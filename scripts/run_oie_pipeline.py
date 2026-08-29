#!/usr/bin/env python3
"""Run the OIE A→B→C pipeline for one pipeline_run_id."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestrate Module A → B → C for one pipeline_run_id"
    )
    parser.add_argument(
        "--cache_file",
        default=os.environ.get("DATABASE_URL")
        or os.environ.get("DEV_DATABASE_URL")
        or "sqlite:///",
        help="SQLAlchemy DB URL (default: DATABASE_URL / DEV_DATABASE_URL / memory)",
    )
    parser.add_argument(
        "--run_id",
        default="",
        help="pipeline_run_id (default: UTC timestamp)",
    )
    parser.add_argument("--skip-a", action="store_true")
    parser.add_argument("--skip-b", action="store_true")
    parser.add_argument("--skip-c", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run stages without persisting queue writes where supported",
    )
    parser.add_argument(
        "--no-sync-repos",
        action="store_true",
        help="skip git clone/fetch during Module A (use local cache as-is)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="run later stages even if an earlier stage errors",
    )
    args = parser.parse_args()

    # Ensure Flask app context for SQLAlchemy.
    os.environ.setdefault("FLASK_CONFIG", "development")
    from cre import app  # noqa: WPS433 — CLI bootstrap

    from application.utils.oie_orchestrator import run_oie_pipeline

    with app.app_context():
        result = run_oie_pipeline(
            cache_file=args.cache_file,
            pipeline_run_id=args.run_id or None,
            skip_a=args.skip_a,
            skip_b=args.skip_b,
            skip_c=args.skip_c,
            dry_run=args.dry_run,
            sync_repos=not args.no_sync_repos,
            stop_on_error=not args.continue_on_error,
        )
    print(result.to_json())
    return 0 if result.to_dict()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
