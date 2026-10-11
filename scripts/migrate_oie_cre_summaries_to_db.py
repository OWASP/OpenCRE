#!/usr/bin/env python3
"""Migrate JSON CRE summary cache into ``oie.summary`` + ``CRE_SUMMARY`` embeddings.

Reads ``CRE_LIBRARIAN_CRE_SUMMARY_CACHE`` (default ``tmp/oie_cre_summaries``) and
writes each blurb into CRE ``document_metadata.oie.summary``. When a cache file
includes an ``embedding`` vector, also upserts ``embeddings`` with
``doc_type=CRE_SUMMARY`` and sets ``oie.embedding_id``.

Never writes ``CRE.description`` or hub ``doc_type=CRE`` embeddings.

Usage (local clone only — refuses the ``cre`` database and Heroku URLs):

  source /Users/sg/Projects/OpenCRE/venv/bin/activate
  set -a; source /Users/sg/Projects/OpenCRE/.env; set +a
  PYTHONPATH=. python scripts/migrate_oie_cre_summaries_to_db.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre_prodclone \\
    --summary-cache tmp/oie_cre_summaries
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _assert_local_clone_url(url: str) -> None:
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/").split("/")[0]
    host = (parsed.hostname or "").lower()
    if "heroku" in url.lower() or "opencreorg" in url.lower():
        raise SystemExit(
            f"refusing production/Heroku URL (host {host!r}); "
            "use cre_prodclone locally"
        )
    if db_name == "cre":
        raise SystemExit(
            "refusing database 'cre'; pass cre_prodclone "
            "(postgresql://cre:password@127.0.0.1:5432/cre_prodclone)"
        )
    if host not in ("127.0.0.1", "localhost", ""):
        raise SystemExit(f"refusing non-local host {host!r}; migrate is local-only")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("DEV_DATABASE_URL", ""),
        help="SQLAlchemy URL (must be local cre_prodclone, never 'cre')",
    )
    parser.add_argument(
        "--summary-cache",
        default=os.environ.get(
            "CRE_LIBRARIAN_CRE_SUMMARY_CACHE", str(_ROOT / "tmp" / "oie_cre_summaries")
        ),
        help="Directory of JSON blurbs to import",
    )
    args = parser.parse_args()
    if not args.cache_file:
        print("DEV_DATABASE_URL / --cache-file required", file=sys.stderr)
        return 2
    _assert_local_clone_url(args.cache_file)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application.cmd.cre_main import db_connect
    from application.utils.librarian.cre_summary import (
        default_cache_dir,
        migrate_json_cache_to_db,
    )

    database = db_connect(args.cache_file)
    cache_dir = Path(args.summary_cache) if args.summary_cache else default_cache_dir()
    n = migrate_json_cache_to_db(database=database, cache_dir=cache_dir)
    print(f"migrated {n} CRE summar(ies) from {cache_dir} into oie.summary", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
