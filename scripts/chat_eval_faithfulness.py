#!/usr/bin/env python3
"""Ragas faithfulness over recorded chat answers (#1078). Optional, local only.

Reads a recording made by ``scripts/chat_eval_gold.py --live --record ...`` and
asks an LLM judge, through Ragas' ``Faithfulness`` metric, whether each claim in
each answer is supported by the passages that answer returned. Prints per-row
scores and the claims the judge found unsupported.

This is not part of ``make test`` and Ragas is not in any requirements file: it
needs a paid LLM judge and its LangChain pins clash with the app's. Install it in
its own virtualenv (see docs/chat_eval.md):

    python3 -m venv .venv-ragas
    .venv-ragas/bin/pip install "ragas==0.4.3" "langchain-community>=0.3,<0.4"
    GEMINI_API_KEY=... .venv-ragas/bin/python scripts/chat_eval_faithfulness.py \\
        --responses tmp/chat_eval/staging.jsonl --output-json tmp/chat_eval/faith.json

The judge is any OpenAI-compatible endpoint. The default is Gemini's
(``--judge-base-url``), keyed by ``--judge-key-env`` (default ``GEMINI_API_KEY``).
Cost: two judge calls per judged row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.ask_eval.faithfulness import (  # noqa: E402
    Judge,
    Statement,
    faithfulness_inputs,
    judge_inputs,
    summarize_faithfulness,
)
from application.utils.ask_eval.gold import load_gold  # noqa: E402
from application.utils.ask_eval.runner import load_records  # noqa: E402

DEFAULT_GOLD = (
    _ROOT
    / "application"
    / "tests"
    / "fixtures"
    / "ask_regressions"
    / "chat_eval_gold.jsonl"
)
GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def ragas_judge(model: str, base_url: str, api_key: str) -> Judge:
    """Ragas ``Faithfulness`` as a judge that also returns per-claim verdicts.

    ``Faithfulness.ascore`` only returns the ratio. The report needs the claims it
    rejected, so this calls the metric's two steps (split the answer into claims,
    then check each claim against the passages) and keeps the verdicts. Those are
    private methods in Ragas 0.4.3; pin that version.
    """
    try:
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import Faithfulness
    except ImportError as exc:  # pragma: no cover - depends on the optional venv
        raise SystemExit(
            f"Ragas is not installed ({exc}). See the install lines at the top "
            "of this script or docs/chat_eval.md."
        )

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    metric = Faithfulness(llm=llm_factory(model, client=client, temperature=0))

    async def judge(
        question: str, answer: str, passages: Sequence[str]
    ) -> List[Statement]:
        claims = await metric._create_statements(question, answer)
        if not claims:
            return []
        verdicts = await metric._create_verdicts(claims, "\n".join(passages))
        return [
            Statement(text=v.statement, supported=bool(v.verdict))
            for v in verdicts.statements
        ]

    return judge


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--responses", required=True, help="recorded JSONL")
    parser.add_argument("--judge-model", default="gemini-2.5-flash")
    parser.add_argument("--judge-base-url", default=GEMINI_OPENAI_URL)
    parser.add_argument("--judge-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--only", help="comma-separated gold ids to judge")
    parser.add_argument("--output-json", help="write the full report here")
    args = parser.parse_args(argv)

    api_key = os.environ.get(args.judge_key_env)
    if not api_key:
        parser.error(f"set {args.judge_key_env} to the judge's API key")

    rows = load_gold(Path(args.gold))
    if args.only:
        wanted = {i.strip() for i in args.only.split(",")}
        rows = [r for r in rows if r.id in wanted]
    inputs, skipped = faithfulness_inputs(rows, load_records(Path(args.responses)))
    judge = ragas_judge(args.judge_model, args.judge_base_url, api_key)
    results = asyncio.run(judge_inputs(inputs, judge))
    summary = summarize_faithfulness(results)

    for res in results:
        score = "error" if res.score is None else f"{res.score:.2f}"
        print(
            f"{res.id:30} {score:>6}  claims={len(res.statements)}"
            f"  passages={res.n_passages} (cut at cap: {res.truncated_passages})"
        )
        for claim in res.unsupported:
            print(f"    unsupported: {claim}")
        if res.error:
            print(f"    {res.error}")
    print("== summary")
    for key in (
        "judged",
        "mean_faithfulness",
        "statements",
        "supported_statements",
        "passages",
        "truncated_passages",
    ):
        print(f"  {key:22} {summary[key]}")
    if skipped:
        print(
            f"  {'skipped':22} " + ", ".join(f"{k} ({v})" for k, v in skipped.items())
        )

    if args.output_json:
        out: dict[str, Any] = {
            "judge": {"model": args.judge_model, "base_url": args.judge_base_url},
            "summary": summary,
            "skipped": skipped,
            "results": [dict(asdict(r), unsupported=r.unsupported) for r in results],
        }
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
