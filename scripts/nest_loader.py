#!/usr/bin/env python3
"""Load OWASP Nest project profiles and GitHub issue titles into the comprehension index.

    python scripts/nest_loader.py --projects              # leaders, level, dates per project (341 calls)
    python scripts/nest_loader.py --issues [--limit N]    # issue titles grouped per repository
    python scripts/nest_loader.py --projects --dry-run    # show what would be written

Needs NEST_API_KEY / NEST_API_BASE (same as the owasp-agent sync). Documents are attached to the
project's repository slug, so they are read together with the rest of that project.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

import requests


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projects", action="store_true")
    ap.add_argument("--issues", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="max issues to read (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    if not (a.projects or a.issues):
        ap.error("choose --projects and/or --issues")

    from application import create_app
    from application.database import db as db_mod
    from application.prompt_client import prompt_client
    from application.utils.comprehension import nest_source as ns
    from application.utils.comprehension import store
    from application.utils.comprehension.shared import shared_handler

    base = os.environ.get("NEST_API_BASE", "https://nest.owasp.org/api/v0").rstrip("/")
    headers = {
        "X-API-Key": os.environ.get("NEST_API_KEY", ""),
        "Accept": "application/json",
    }
    if not headers["X-API-Key"]:
        print("NEST_API_KEY is required", file=sys.stderr)
        return 2

    def get(path: str):
        r = requests.get(f"{base}/{path.lstrip('/')}", headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()

    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        handler = shared_handler(database)
        from sqlalchemy import text as sql_text

        repos = sorted(
            r[0]
            for r in database.session.execute(
                sql_text(
                    "SELECT DISTINCT source_repo FROM harvest_input WHERE source_repo LIKE 'OWASP/%'"
                )
            )
        )
        today = datetime.date.today().isoformat()

        if a.projects:
            items = list(ns.iter_items(get, "projects/"))
            mapping = ns.map_projects_to_repos([i["key"] for i in items], repos)
            print(
                f"nest projects: {len(items)}; matched to a repository: {len(mapping)}",
                flush=True,
            )
            written = 0
            for it in items:
                repo = mapping.get(it["key"])
                if not repo:
                    continue
                try:
                    detail = get(f"projects/{it['key']}")
                except Exception as exc:  # noqa: BLE001
                    print(f"{it['key']}: detail failed {str(exc)[:80]}", flush=True)
                    continue
                text = ns.profile_text(detail, today)
                chunk = [("nest/project-profile.md", 0, text)]
                url = f"https://nest.owasp.org/projects/{it['key']}"
                written += store.write_raw(
                    database,
                    repo,
                    chunk,
                    handler.get_text_embeddings,
                    workers=1,
                    dry_run=a.dry_run,
                    url_for=lambda _p, u=url: u,
                )
            print(f"project profiles written: {written}", flush=True)

        if a.issues:
            grouped = ns.issues_by_repo(ns.iter_items(get, "issues/"), limit=a.limit)
            print(f"repos with issues: {len(grouped)}", flush=True)
            total = 0
            known = {r.lower(): r for r in repos}
            for slug_repo, issues in sorted(grouped.items()):
                repo = known.get(slug_repo.lower())
                if not repo:
                    continue
                chunks = [
                    ("nest/issues.md", i, t)
                    for i, t in enumerate(ns.issue_chunks(issues))
                ]
                url = f"https://github.com/{repo}/issues"
                total += store.write_raw(
                    database,
                    repo,
                    chunks,
                    handler.get_text_embeddings,
                    workers=a.workers,
                    dry_run=a.dry_run,
                    url_for=lambda _p, u=url: u,
                )
            print(f"issue chunks written: {total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
