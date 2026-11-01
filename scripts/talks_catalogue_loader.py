#!/usr/bin/env python3
"""Index a talk catalogue (one video per line: id|YYYYMMDD|seconds|title) as retrievable documents.

    python scripts/talks_catalogue_loader.py catalogue.txt [--repo OWASP/youtube-talks] [--dry-run]

The catalogue comes from  yt-dlp --flat-playlist --extractor-args youtubetab:approximate_date
--print '%(id)s|%(upload_date)s|%(duration)s|%(title)s'  <channel>/videos . Dates from that listing are
approximate (YouTube only shows "N years ago"), so documents say so. Captions are not fetched.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalogue")
    ap.add_argument("--repo", default="OWASP/youtube-talks")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    from application import create_app
    from application.database import db as db_mod
    from application.utils.comprehension import store
    from application.utils.comprehension.shared import shared_handler
    from application.utils.comprehension.talks_source import (
        catalogue_chunks,
        parse_catalogue,
    )

    with open(a.catalogue, encoding="utf-8") as fh:
        talks = parse_catalogue(fh.read())
    chunks = catalogue_chunks(talks)
    print(f"talks: {len(talks)} chunks: {len(chunks)}", flush=True)
    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        n = store.write_raw(
            database,
            a.repo,
            chunks,
            shared_handler(database).get_text_embeddings,
            workers=a.workers,
            dry_run=a.dry_run,
            url_for=lambda _p: "https://www.youtube.com/@OWASPGLOBAL/videos",
        )
    print(f"catalogue chunks {'planned' if a.dry_run else 'written'}: {n}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
