#!/usr/bin/env python3
"""Merge near-duplicate OWASP agent concepts (strict anti-sprawl cron target)."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge near-duplicate owasp_agent concepts"
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("OWASP_AGENT_DB", "tmp/owasp_agent.sqlite"),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(os.environ.get("OWASP_AGENT_MERGE_THRESHOLD", "0.85")),
    )
    args = parser.parse_args()

    from application.utils.owasp_agent.concepts import merge_near_duplicate_concepts
    from application.utils.owasp_agent.index_store import IndexStore

    store = IndexStore(args.db)
    merges = merge_near_duplicate_concepts(store, threshold=args.threshold)
    print(
        json.dumps(
            {
                "merged": [{"from": a, "into": b, "reason": r} for a, b, r in merges],
                "count": len(merges),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
