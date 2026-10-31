#!/usr/bin/env python3
"""Seed the external-source registry with curated OWASP event/chapter sites, as SUGGESTIONS.

    python scripts/seed_event_sources.py            # dry run (default): print what would be added
    python scripts/seed_event_sources.py --apply    # write disabled, suggested targets
    python scripts/seed_event_sources.py --file other.json --limit 10

Reads docs/oie/owasp-event-sites.json (see docs/oie/owasp-event-sites.md). Never fetches anything;
hosts that are already registered, approved or rejected are skipped. Nothing is crawled until an
admin accepts the suggestion in the Admin panel.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from application.utils.comprehension import discovery, event_seed  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=event_seed.DEFAULT_PATH)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--limit", type=int, default=discovery.DEFAULT_LIMIT)
    a = ap.parse_args(argv)

    cands = event_seed.candidates(event_seed.load_sites(a.file))

    from application import create_app, sqla

    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        for p in event_seed.plan(cands, sqla.session):
            c = p["candidate"]
            print(
                f"{p['action']:6} {p['id']:36} {c['url']}  refresh={c['refresh_days']}d "
                f"pages={c['max_pages']} {p['why']}".rstrip(),
                flush=True,
            )
        if not a.apply:
            print("dry run: nothing written (use --apply)")
            return 0
        res = event_seed.apply(cands, sqla.session, limit=a.limit)
        print(
            f"created {len(res['created'])}, merged {len(res['merged'])}, "
            f"skipped {len(res['skipped'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
