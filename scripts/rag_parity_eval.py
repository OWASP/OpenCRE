#!/usr/bin/env python3
"""Phase 6: offline gold bridge metrics (no paid LLM path by default)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.rag_parity.phase6_eval import (  # noqa: E402
    GoldCase,
    reports_to_dict,
    run_deepeval_bridge,
    run_ragas_bridge,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold-json",
        help="Optional JSON list of {query, expected_cre_ids}",
    )
    parser.add_argument("--output-json", default="tmp/rag_parity_eval.json")
    args = parser.parse_args()
    if args.gold_json:
        raw = json.loads(Path(args.gold_json).read_text(encoding="utf-8"))
        cases = [
            GoldCase(
                query=str(item["query"]),
                expected_cre_ids=list(item.get("expected_cre_ids") or []),
            )
            for item in raw
        ]
    else:
        cases = [
            GoldCase("password length", ["demo-111"]),
            GoldCase("session binding", ["demo-222"]),
        ]

    def retrieve(q: str):
        # Hermetic stub — replace with evaluate_librarian / pgvector on homeserver.
        if "password" in q.lower():
            return ["demo-111"]
        if "session" in q.lower():
            return ["demo-222"]
        return []

    reports = [
        run_ragas_bridge(cases, retrieve),
        run_deepeval_bridge(cases, retrieve),
    ]
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = reports_to_dict(reports)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
