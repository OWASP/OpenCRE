#!/usr/bin/env python3
"""Manual check of speaker/event extraction on a catalogue export (no writes).

    python scripts/youtube_extract_eval.py --catalogue /tmp/yt_catalogue.json --sample 40

Calls the LLM (gemini-2.5-flash-lite) only when GEMINI_API_KEY is set; otherwise prints what it would do
and the estimated cost. Prints one record per video plus how many found a speaker / event / date.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from typing import List, Optional

from application.utils.comprehension import youtube_extract as yx


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cache-dir", default=".youtube-cache/extract")
    a = ap.parse_args(argv)

    videos = yx.videos_from_catalogue(a.catalogue)
    random.Random(a.seed).shuffle(videos)
    videos = videos[: a.sample]
    ex = yx.Extractor(
        yx.default_llm() if os.environ.get("GEMINI_API_KEY") else (lambda s, u: ""),
        cache_dir=a.cache_dir,
    )
    print(yx.describe_run(videos, ex))
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set: nothing called")
        return 0
    ex.run(videos)
    got = [v for v in videos if v.extracted]
    for v in videos:
        x = v.extracted or {}
        print(
            f"- {v.title[:80]}\n    speakers={x.get('speakers')} event={x.get('event')!r} "
            f"date={x.get('event_date')!r} kind={x.get('kind')} conf={x.get('confidence')}"
        )
    print(
        f"extracted {len(got)}/{len(videos)}; with speaker "
        f"{sum(bool(v.extracted['speakers']) for v in got)}, event "
        f"{sum(bool(v.extracted['event']) for v in got)}, date "
        f"{sum(bool(v.extracted['event_date']) for v in got)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
