#!/usr/bin/env python3
"""Migrate librarian LLM JSON disk caches into ``oie_llm_cache``.

Imports (when present):
  tmp/oie_shortlist_judge_cache/*.json  → kind=shortlist_judge
  tmp/oie_edition_remap_cache/*.json    → kind=edition_remap
  tmp/oie_neighbor_remap_cache/*.json   → kind=neighbor_remap

Local clone only (refuses ``cre`` DB / Heroku). After migrate, leave the
``CRE_LIBRARIAN_*_CACHE`` env vars unset so workers use Postgres only.

  PYTHONPATH=. python scripts/migrate_oie_llm_caches_to_db.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre_prodclone
"""

from __future__ import annotations

import argparse
import json
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
        raise SystemExit(f"refusing production/Heroku URL (host {host!r})")
    if db_name == "cre":
        raise SystemExit("refusing database 'cre'; use cre_prodclone locally")
    if host not in ("127.0.0.1", "localhost", ""):
        raise SystemExit(f"refusing non-local host {host!r}")


def _import_dir(database: object, kind: str, directory: Path) -> int:
    if not directory.is_dir():
        return 0
    n = 0
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        key = path.stem
        # Edition remap filenames replace ':' / '>' for disk safety; restore
        # is best-effort — stem is already the storage key used by get/put.
        if database.put_oie_llm_cache(kind, key, payload):
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("DEV_DATABASE_URL", ""),
        help="SQLAlchemy URL (local cre_prodclone)",
    )
    parser.add_argument(
        "--shortlist-dir",
        default=str(_ROOT / "tmp" / "oie_shortlist_judge_cache"),
    )
    parser.add_argument(
        "--edition-dir",
        default=str(_ROOT / "tmp" / "oie_edition_remap_cache"),
    )
    parser.add_argument(
        "--neighbor-dir",
        default=str(_ROOT / "tmp" / "oie_neighbor_remap_cache"),
    )
    args = parser.parse_args()
    if not args.cache_file:
        print("DEV_DATABASE_URL / --cache-file required", file=sys.stderr)
        return 2
    _assert_local_clone_url(args.cache_file)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application.cmd.cre_main import db_connect
    from application.utils.librarian.llm_response_cache import (
        KIND_EDITION_REMAP,
        KIND_NEIGHBOR_REMAP,
        KIND_SHORTLIST_JUDGE,
    )

    database = db_connect(args.cache_file)
    counts = {
        KIND_SHORTLIST_JUDGE: _import_dir(
            database, KIND_SHORTLIST_JUDGE, Path(args.shortlist_dir)
        ),
        KIND_EDITION_REMAP: _import_dir(
            database, KIND_EDITION_REMAP, Path(args.edition_dir)
        ),
        KIND_NEIGHBOR_REMAP: _import_dir(
            database, KIND_NEIGHBOR_REMAP, Path(args.neighbor_dir)
        ),
    }
    print(json.dumps({"migrated": counts}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
