#!/usr/bin/env python3
"""CLI for the OIE PoC orchestrator (Module A → B → C).

Examples (local / demo):

  # Librarian-only dry-run (works on main today with fixture JSONL)
  python scripts/run_oie_demo_pipeline.py \\
      --cache_file "$DATABASE_URL" \\
      --skip-a --skip-b \\
      --librarian-source application/tests/librarian/fixtures/sample_knowledge_queue.jsonl

  # Full sequence once Module B #989 (and ideally Module A entry) are available
  python scripts/run_oie_demo_pipeline.py \\
      --cache_file "$DATABASE_URL" \\
      --run-id demo-2026-07-24 \\
      --skip-a

See application/utils/oie_orchestrator/pipeline.py for per-module TODO markers.
Does not modify Modules A/B/C — only calls their entry points when present.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Allow running directly as `python scripts/run_oie_demo_pipeline.py`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PoC orchestrator: Module A (harvester) → B (noise filter) → C (librarian)."
    )
    parser.add_argument(
        "--cache_file",
        default=os.environ.get("DATABASE_URL", "sqlite:////tmp/cre_oie_demo.db"),
        help="SQLAlchemy DB URL (same as cre.py --cache_file)",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="pipeline_run_id shared across stages (default: random UUID)",
    )
    parser.add_argument(
        "--skip-a",
        action="store_true",
        default=True,
        help="skip Module A (default: true — no harvester entry point yet)",
    )
    parser.add_argument(
        "--run-a",
        action="store_true",
        help="attempt Module A (records TODO until harvester entry lands)",
    )
    parser.add_argument("--skip-b", action="store_true", help="skip Module B")
    parser.add_argument("--skip-c", action="store_true", help="skip Module C")
    parser.add_argument(
        "--librarian-source",
        default=None,
        help="knowledge_queue JSONL for Module C (fixture until DB source / W8)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="disable dry_run where a module supports writes (B queue / C links). "
        "C still cannot write links pre-W8.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from application.utils.oie_orchestrator import run_oie_demo_pipeline

    result = run_oie_demo_pipeline(
        cache_file=args.cache_file,
        pipeline_run_id=args.run_id or None,
        skip_a=not args.run_a,
        skip_b=args.skip_b,
        skip_c=args.skip_c,
        librarian_source_jsonl=args.librarian_source,
        dry_run=not args.write,
    )
    print(result.to_json())
    return 0 if result.to_dict()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
