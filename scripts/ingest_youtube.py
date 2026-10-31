#!/usr/bin/env python3
"""Ingest approved YouTube channels (catalogue + captions) into the comprehension index.

    python scripts/ingest_youtube.py                       # dry run over approved youtube_channel targets
    python scripts/ingest_youtube.py --spec-json spec.json --captions-dir ./captions --limit 20
    python scripts/ingest_youtube.py --apply               # embed and write
    python scripts/ingest_youtube.py --extract             # dry run: LLM calls, tokens and cost for speaker/event extraction
    python scripts/ingest_youtube.py --extract --sample 5 --fixture /tmp/yt_catalogue.json   # show records, write nothing
    python scripts/ingest_youtube.py --apply --extract     # rewrite catalogue chunks (same ids, so they replace the old ones)

Needs YOUTUBE_API_KEY (YouTube Data API v3, 1 quota unit per list call). Captions come from exported
``<video_id>.<lang>.vtt|srt`` files in --captions-dir; with the optional YOUTUBE_OAUTH_* variables
set, videos of channels we own can also be fetched through captions.download (drip limited).
The default is a dry run: nothing is embedded or written. See docs/oie/youtube-source.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List, Optional, Tuple

from application.utils.comprehension import external as ext
from application.utils.comprehension import youtube_extract as yx
from application.utils.comprehension import youtube_source as ys

CHARS_PER_TOKEN = 4.0
EMBED_PRICE_PER_M = 0.15  # USD per million tokens (cost.PRICE["embed_in"])
# Earlier pilot: ~$16 for ~1,600 talks including LLM enrichment, i.e. about a cent per talk.
PILOT_USD_PER_TALK = 0.01


def load_people(path: str) -> List[str]:
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip()]


def collect(
    spec: ext.ExternalSpec,
    api: ys.YouTubeApi,
    captions_dir: str,
    people: List[str],
    limit: int,
    downloader: Any = None,
    extractor: Optional[yx.Extractor] = None,
) -> Tuple[List[ys.Video], List[Tuple[str, int, str]], int]:
    """(videos, chunks, videos_with_captions) for one channel spec."""
    videos = api.channel_videos(spec, limit=limit)
    ys.link_speakers(videos, people)
    if extractor is not None:
        extractor.run(videos)
    chunks: List[Tuple[str, int, str]] = []
    with_captions = 0
    for v in videos:
        cues = ys.read_captions(captions_dir, v.id)
        if not cues and downloader is not None:
            cues = downloader.fetch(v.id)
        with_captions += bool(cues)
        chunks += ys.video_chunks(v, cues, spec.name)
    return videos, chunks, with_captions


def print_sample(videos: List[ys.Video], n: int, extractor: yx.Extractor) -> None:
    """Extracted records for the first ``n`` videos; needs GEMINI_API_KEY unless cached. Writes nothing."""
    chosen = videos[:n]
    if extractor.pending(chosen) and not os.environ.get("GEMINI_API_KEY"):
        print(
            f"sample: {len(extractor.pending(chosen))} of {len(chosen)} videos need an LLM call but "
            "GEMINI_API_KEY is not set; nothing called",
            flush=True,
        )
        return
    extractor.run(chosen)
    for v in chosen:
        print(
            json.dumps({"id": v.id, "title": v.title, "extracted": v.extracted}),
            flush=True,
        )


def open_database() -> Any:
    from application import create_app
    from application.database import db as db_mod

    create_app(mode=os.environ.get("FLASK_CONFIG", "production")).app_context().push()
    return db_mod.Node_collection()


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--spec-json", help="a single ExternalSpec as JSON (file path or inline)"
    )
    ap.add_argument(
        "--captions-dir", default=os.environ.get("YOUTUBE_CAPTIONS_DIR", "")
    )
    ap.add_argument(
        "--cache-dir", default=".youtube-cache", help="API responses and OAuth state"
    )
    ap.add_argument(
        "--people-file",
        default="",
        help="speaker names, one per line (e.g. Nest leaders)",
    )
    ap.add_argument(
        "--limit", type=int, default=0, help="max videos per channel (0 = all)"
    )
    ap.add_argument(
        "--apply", action="store_true", help="embed and write (default: dry run)"
    )
    ap.add_argument(
        "--force-delete",
        action="store_true",
        help="allow deleting more than half of a source's stored videos "
        "(videos made private/deleted are removed on a full --apply run)",
    )
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--extract",
        action="store_true",
        help="LLM-extract speakers/event/date from titles and descriptions (dry run prints cost)",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=0,
        help="with --extract: print N extracted records",
    )
    ap.add_argument(
        "--fixture",
        default="",
        help="with --extract: a catalogue JSON export instead of the YouTube API (never writes)",
    )
    a = ap.parse_args(argv)

    extractor = None
    if a.extract:
        extractor = yx.Extractor(
            yx.default_llm() if (a.apply or a.sample) else (lambda s, u: ""),
            cache_dir=os.path.join(a.cache_dir, "extract"),
        )
    if a.fixture:
        if not extractor:
            ap.error("--fixture needs --extract")
        videos = yx.videos_from_catalogue(a.fixture, a.limit)
        print(yx.describe_run(videos, extractor), flush=True)
        if a.sample:
            print_sample(videos, a.sample, extractor)
        print("fixture mode: nothing written", flush=True)
        return 0

    people = load_people(a.people_file)
    api = ys.YouTubeApi(cache_dir=os.path.join(a.cache_dir, "api"))
    limiter = ys.DripLimiter(os.path.join(a.cache_dir, "caption-downloads.json"))
    downloader = ys.CaptionDownloader(
        limiter, out_dir=a.captions_dir or os.path.join(a.cache_dir, "captions")
    )

    database = None
    if a.spec_json:
        raw = a.spec_json
        if os.path.isfile(raw):
            with open(raw, encoding="utf-8") as fh:
                raw = fh.read()
        specs = [ext.validate_spec({**json.loads(raw), "kind": ext.KIND_YOUTUBE})]
    else:
        database = open_database()
        specs = ext.load_specs(database.session, kinds=(ext.KIND_YOUTUBE,))
    if not specs:
        print("no approved youtube_channel sources", flush=True)
        return 0

    written = 0
    failed = 0
    for spec in specs:
        if not spec.playlist_id and ys.handle_of(spec.channel_id):
            try:
                resolved = api.resolve_channel_id(spec.channel_id)
            except (ValueError, RuntimeError) as exc:
                print(f"{ext.slug_for(spec)}: {exc}", file=sys.stderr, flush=True)
                failed += 1
                continue
            print(
                f"{ext.slug_for(spec)}: resolved {spec.channel_id} -> {resolved}",
                flush=True,
            )
            spec.channel_id = resolved
        videos, chunks, with_caps = collect(
            spec,
            api,
            a.captions_dir,
            people,
            a.limit,
            downloader if downloader.enabled() else None,
            extractor=extractor if a.apply else None,
        )
        if extractor is not None:
            if not a.apply:
                print(yx.describe_run(videos, extractor), flush=True)
            if a.sample:
                print_sample(videos, a.sample, extractor)
        chars = sum(len(c[2]) for c in chunks)
        tokens = chars / CHARS_PER_TOKEN
        print(
            f"{ext.slug_for(spec)}: videos={len(videos)} with_captions={with_caps} "
            f"catalogue_only={len(videos) - with_caps} chunks={len(chunks)} "
            f"est_tokens={int(tokens)} embed_cost_usd={tokens * EMBED_PRICE_PER_M / 1e6:.4f} "
            f"pilot_rate_cost_usd={len(videos) * PILOT_USD_PER_TALK:.2f} "
            f"api_quota_units={api.quota_used}",
            flush=True,
        )
        if not a.apply:
            continue
        if database is None:
            database = open_database()
        from application.utils.comprehension import store
        from application.utils.comprehension.shared import shared_handler

        written += store.write_raw(
            database,
            ext.slug_for(spec),
            chunks,
            shared_handler(database).get_text_embeddings,
            workers=a.workers,
            url_for=lambda p, s=spec: ext.page_url(s, p),
        )
        if a.limit:
            print("--limit set: partial run, not removing stale videos", flush=True)
        else:
            try:
                gone = store.delete_stale_raw(
                    database, ext.slug_for(spec), chunks, force=a.force_delete
                )
                print(
                    f"{ext.slug_for(spec)}: removed {gone} chunks of videos no longer on YouTube",
                    flush=True,
                )
            except ValueError as exc:
                print(
                    f"{ext.slug_for(spec)}: stale cleanup skipped: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                failed += 1
    print(
        f"chunks written: {written}" if a.apply else "dry run: nothing written",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
