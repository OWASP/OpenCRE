#!/usr/bin/env python3
"""Suggest external knowledge sources (project sites, YouTube channels) from links in harvested repos.

    python scripts/suggest_external_sources.py [--top 30] [--like 'OWASP/www-project-%'] [--apply]

Reads the already-harvested chunks of every repo (no network, nothing is crawled). The default is a dry
run that prints the top candidates; --apply stores them as ``suggested`` (disabled) external targets for
the admin to accept or reject in the Workbench.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--like", help="only repos whose source_repo matches this SQL ILIKE"
    )
    ap.add_argument("--top", type=int, default=30, help="candidates to print")
    ap.add_argument("--limit", type=int, default=25, help="max new suggestions stored")
    ap.add_argument(
        "--apply", action="store_true", help="write suggestions (default: dry run)"
    )
    a = ap.parse_args()

    from application import create_app
    from application.database import db as db_mod
    from application.utils.comprehension import discovery

    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        res = discovery.suggest_from_repos(
            database.session, a.limit, like=a.like, apply=a.apply
        )
        cands = res["ranked"]
        print(f"{res['repos']} repos, {len(cands)} candidates", flush=True)
        for c in cands[: a.top]:
            first = c["found_in"][0]
            print(
                f"{c['score']:6.2f}  {c['kind']:7}  {c['host']:32}  "
                f"{len({f['repo'] for f in c['found_in']})} repo(s)  "
                f"{first['repo']}:{first['file']}  [{first['link_text']}]",
                flush=True,
            )
        if a.apply:
            print(
                f"applied: {len(res['created'])} new, {len(res['merged'])} merged, "
                f"{len(res['skipped'])} skipped, {res['resolved']} redirects resolved",
                flush=True,
            )
        else:
            print("dry run; pass --apply to store suggestions", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
