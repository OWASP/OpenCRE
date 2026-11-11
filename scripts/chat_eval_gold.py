#!/usr/bin/env python3
"""Score OpenCRE chat on the #1078 gold set.

Recorded mode (default, no network, no LLM):

    python scripts/chat_eval_gold.py --responses tmp/chat_eval/current.jsonl

Live mode asks a running OpenCRE and records what it said, so the run can be
re-scored later without calling the LLM again:

    OPENCRE_API_KEY=... python scripts/chat_eval_gold.py --live \\
        --base-url http://127.0.0.1:5000 --record tmp/chat_eval/current.jsonl

``--baseline other.jsonl`` scores a second recording and prints which cases
flipped, e.g. current single-passage chat vs #1161 top-k.

Live mode costs one LLM call per gold row (24 today). Use NO_LOGIN=1 on a local
server, or an API key in OPENCRE_API_KEY for a deployed one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.ask_eval.gold import load_gold  # noqa: E402
from application.utils.ask_eval.runner import (  # noqa: E402
    compare_reports,
    fetch_live,
    load_records,
    score_records,
    write_records,
)

DEFAULT_GOLD = (
    _ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "ask_regressions"
    / "chat_eval_gold.jsonl"
)


def _print_report(label: str, report: dict) -> None:
    print(f"== {label}")
    for key in (
        "n",
        "passed",
        "cre_recall",
        "cre_precision",
        "cite_group_recall",
        "abstain_correct",
        "false_abstain",
    ):
        print(f"  {key:18} {report.get(key)}")
    for key in ("bad_marker_cases", "failed", "missing"):
        if report.get(key):
            print(f"  {key:18} {', '.join(report[key])}")
    if report.get("errors"):
        errs = ", ".join(f"{k}={v}" for k, v in report["errors"].items())
        print(f"  {'errors':18} {errs}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--responses", help="recorded JSONL to score")
    parser.add_argument("--live", action="store_true", help="ask a running server")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--record", help="where live mode writes its JSONL")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--baseline", help="second recording to compare against")
    parser.add_argument("--output-json", help="write the full report here")
    args = parser.parse_args(argv)

    if args.live == bool(args.responses):
        parser.error("use exactly one of --responses or --live")

    rows = load_gold(Path(args.gold))
    if args.live:
        if not args.record:
            parser.error("--live needs --record so the run can be re-scored")
        records = fetch_live(
            rows,
            args.base_url,
            token=os.environ.get("OPENCRE_API_KEY"),
            timeout=args.timeout,
        )
        write_records(Path(args.record), records)
        print(f"recorded {len(records)} responses to {args.record}")
    else:
        records = load_records(Path(args.responses))

    report = score_records(rows, records)
    out = {"run": report}
    if args.baseline:
        base = score_records(rows, load_records(Path(args.baseline)))
        _print_report(f"baseline {args.baseline}", base)
        out["baseline"] = base
        out["compare"] = compare_reports(base, report)
    _print_report(args.record or args.responses, report)
    if args.baseline:
        cmp = out["compare"]
        print(f"== fixed: {', '.join(cmp['fixed']) or '-'}")
        print(f"== broken: {', '.join(cmp['broken']) or '-'}")

    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
