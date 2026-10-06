#!/usr/bin/env python3
"""Sync Nest + GitHub OWASP metadata into the local owasp_agent index."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync OWASP Nest/GitHub metadata index"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Postgres URL for the meta index (default: DATABASE_URL / DEV_DATABASE_URL)",
    )
    parser.add_argument("--skip-nest", action="store_true")
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument(
        "--chapter-repo",
        action="append",
        default=[],
        help="GitHub full_name to crawl as chapter (repeatable)",
    )
    parser.add_argument(
        "--project-repo",
        action="append",
        default=[],
        help="GitHub full_name to crawl as project (repeatable)",
    )
    parser.add_argument(
        "--auto-concepts",
        action="store_true",
        help="After sync, strictly auto-create concepts from indexed entities",
    )
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application.utils.owasp_agent.concepts import auto_concepts_from_index
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.sync import sync_all

    store = IndexStore(args.db)
    report = sync_all(
        store=store,
        skip_nest=args.skip_nest,
        skip_github=args.skip_github,
        github_chapter_repos=args.chapter_repo or None,
        github_project_repos=args.project_repo or None,
    )
    concept_actions = []
    if args.auto_concepts:
        concept_actions = [
            {"action": a.action, "key": a.concept_key, "detail": a.detail}
            for a in auto_concepts_from_index(store)
        ]
    print(
        json.dumps(
            {"sync": report.to_dict(), "concepts": concept_actions},
            indent=2,
        )
    )
    return 0 if (report.nest_ok or report.github_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
