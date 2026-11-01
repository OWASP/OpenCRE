#!/usr/bin/env python3
"""Precompute edition + neighbor remap LLM caches into ``oie_llm_cache``.

Run once after hub sync / oie-tag-base (local clone). Live Module C then uses
``llm_fn=None`` (cache + heuristic) so C.1 prior-cage does not call Gemini Pro
per miss.

  PYTHONPATH=. python scripts/oie_precompute_remap_caches.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre_prodclone

Refuses production ``cre`` / Heroku URLs.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("DEV_DATABASE_URL", ""),
        help="SQLAlchemy URL (local cre_prodclone)",
    )
    parser.add_argument(
        "--skip-edition",
        action="store_true",
        help="Only warm neighbor topic remaps",
    )
    parser.add_argument(
        "--skip-neighbor",
        action="store_true",
        help="Only warm edition remaps",
    )
    args = parser.parse_args()
    if not args.cache_file:
        print("DEV_DATABASE_URL / --cache-file required", file=sys.stderr)
        return 2
    _assert_local_clone_url(args.cache_file)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application.cmd.cre_main import db_connect
    from application.utils.librarian.edition_remap import (
        build_edition_transfer_from_db,
        default_litellm_fn,
    )
    from application.utils.librarian.neighbor_transfer import (
        build_neighbor_transfer_index,
    )

    database = db_connect(args.cache_file)
    session = database.session
    llm = default_litellm_fn()
    report: dict = {}

    if not args.skip_edition:
        svc = build_edition_transfer_from_db(session, llm_fn=llm, database=database)
        n = svc.precompute_all_remaps()
        report["edition_pairs"] = n
        print(f"edition remaps warmed: {n}", flush=True)

    if not args.skip_neighbor:
        idx = build_neighbor_transfer_index(session, llm_fn=llm, database=database)
        n = idx.precompute_topic_remaps()
        report["neighbor_section_queries"] = n
        print(f"neighbor topic remaps warmed: {n}", flush=True)

    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
