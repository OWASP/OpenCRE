#!/usr/bin/env python3
"""
Check the scheduled OIE jobs (``cre.py --run_scheduled``) straight from the DB.

Reports each job's state (ok / running / stale / failing / never_ran) and the
backlog in the harvest, knowledge and decision queues. The admin API needs a
login, so this reads ``oie_run`` directly instead.

Exit codes:
  0 — every job is ok (or currently running)
  1 — a job is stale, failing, or has never run
  2 — configuration or database failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--database-url",
        default=os.environ.get("CRE_CACHE_FILE", ""),
        help="Postgres URL (default: $CRE_CACHE_FILE)",
    )
    parser.add_argument("--output-json", default="")
    return parser.parse_args(argv)


def render(report: Dict[str, Any]) -> str:
    lines = ["OIE scheduler: " + ("healthy" if report["healthy"] else "ATTENTION")]
    for name, job in report["jobs"].items():
        last = job["last_run"]["id"] if job["last_run"] else "-"
        lines.append(
            f"  {name:<14} {job['state']:<9} last_run={last} "
            f"last_success={job['last_success_at'] or '-'}"
        )
    queues = ", ".join(f"{k}={v}" for k, v in report["queues"].items())
    lines.append(f"  queues: {queues}")
    return "\n".join(lines)


def check(session: Any, output_json: str = "") -> int:
    from application.utils.oie_scheduler.health import evaluate_health

    report = evaluate_health(session)
    print(render(report))
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["healthy"] else 1


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    if not args.database_url:
        print("--database-url or CRE_CACHE_FILE is required", file=sys.stderr)
        return 2
    try:
        from application.cmd.cre_main import db_connect

        collection = db_connect(args.database_url)
        return check(collection.session, args.output_json)
    except Exception as exc:  # noqa: BLE001 -- surfaced as exit code 2
        print(f"could not read OIE health: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
