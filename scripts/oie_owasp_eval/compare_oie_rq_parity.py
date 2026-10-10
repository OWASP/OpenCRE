#!/usr/bin/env python3
"""Compare serial vs RQ OIE run summaries (wall-clock + decision counts).

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/compare_oie_rq_parity.py \\
    --baseline tmp/oie_owasp_eval/experiments/safety_reingest/golden_decision_summary.json \\
    --baseline-minutes 163.6 \\
    --rq-summary path/to/rq_orchestrator.json \\
    --rq-minutes 40.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _load(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", required=True, help="JSON with linked/review counts")
    p.add_argument("--baseline-minutes", type=float, required=True)
    p.add_argument(
        "--rq-summary", required=True, help="RQ orchestrator JSON or decision summary"
    )
    p.add_argument("--rq-minutes", type=float, required=True)
    p.add_argument(
        "--linked-tol",
        type=float,
        default=0.0,
        help="allowed relative drop in linked (0 = no drop)",
    )
    args = p.parse_args()

    base = _load(args.baseline)
    rq = _load(args.rq_summary)
    b_linked = int(base.get("linked") or 0)
    r_linked = int(rq.get("linked") or 0)
    # Orchestrator result may nest stage summaries — allow flat decision summary only.
    if "linked" not in rq and isinstance(rq.get("stages"), list):
        print(
            "RQ summary has stages but no linked count; pass a decision_queue summary JSON.",
            file=sys.stderr,
        )
        return 2

    speedup = (
        args.baseline_minutes / args.rq_minutes if args.rq_minutes > 0 else float("inf")
    )
    min_linked = b_linked * (1.0 - args.linked_tol)
    ok_acc = r_linked >= min_linked
    ok_speed = args.rq_minutes < args.baseline_minutes

    print("## OIE RQ parity")
    print(
        f"- baseline linked={b_linked} review={base.get('review')} wall={args.baseline_minutes:.1f}m"
    )
    print(
        f"- rq       linked={r_linked} review={rq.get('review')} wall={args.rq_minutes:.1f}m"
    )
    print(f"- speedup  {speedup:.2f}x (baseline/rq)")
    if ok_acc and ok_speed:
        print("- verdict  PASS (same-or-better linked, faster wall-clock)")
        return 0
    if not ok_acc:
        delta = r_linked - b_linked
        print(
            f"- ELI5 accuracy: linked changed by {delta:+d}. "
            "If RQ is lower, possible causes: content_hash collisions across "
            "parallel B jobs dropping duplicate text, or a failed artifact job. "
            "If higher, parallel drain may have finished rows the serial run "
            "left errored — check errored counts."
        )
    if not ok_speed:
        print("- ELI5 speed: RQ was not faster; check worker count / Gemini 429s.")
    print("- verdict  FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
