"""Ingest one YouTube channel (shared by scripts/ingest_youtube.py and the scheduled ``external_sources`` job).

A full run replaces the channel's chunks and removes those of videos YouTube no longer returns
(private or deleted), because stored API data must be refreshed or deleted within 30 days.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from application.utils.comprehension import external as ext
from application.utils.comprehension import youtube_extract as yx
from application.utils.comprehension import youtube_source as ys

DEFAULT_CACHE_DIR = ".youtube-cache"


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


def refresh_channel(
    spec: ext.ExternalSpec,
    database: Any,
    *,
    embed: Any,
    apply: bool,
    cache_dir: str = "",
    captions_dir: str = "",
    people_file: str = "",
    extract: bool = True,
    force_delete: bool = False,
    workers: int = 8,
) -> Dict[str, int]:
    """Re-read a channel from the Data API and (when ``apply``) replace its chunks and drop stale ones."""
    from application.utils.comprehension import store

    cache_dir = cache_dir or os.environ.get("YOUTUBE_CACHE_DIR") or DEFAULT_CACHE_DIR
    captions_dir = captions_dir or os.environ.get("YOUTUBE_CAPTIONS_DIR", "")
    people_file = people_file or os.environ.get("YOUTUBE_PEOPLE_FILE", "")
    api = ys.YouTubeApi(cache_dir=os.path.join(cache_dir, "api"))
    if not spec.playlist_id and ys.handle_of(spec.channel_id):
        spec.channel_id = api.resolve_channel_id(spec.channel_id)
    limiter = ys.DripLimiter(os.path.join(cache_dir, "caption-downloads.json"))
    downloader = ys.CaptionDownloader(
        limiter, out_dir=captions_dir or os.path.join(cache_dir, "captions")
    )
    extractor = (
        yx.Extractor(yx.default_llm(), cache_dir=os.path.join(cache_dir, "extract"))
        if extract and apply
        else None
    )
    videos, chunks, _ = collect(
        spec,
        api,
        captions_dir,
        load_people(people_file),
        0,
        downloader if downloader.enabled() else None,
        extractor,
    )
    out = {"videos": len(videos), "chunks": len(chunks), "written": 0, "removed": 0}
    if not apply:
        return out
    slug = ext.slug_for(spec)
    out["written"] = store.write_raw(
        database,
        slug,
        chunks,
        embed,
        workers=workers,
        url_for=lambda p, s=spec: ext.page_url(s, p),
    )
    out["removed"] = store.delete_stale_raw(database, slug, chunks, force=force_delete)
    return out
