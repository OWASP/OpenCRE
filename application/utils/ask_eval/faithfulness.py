"""Faithfulness inputs and report for recorded chat answers (#1078).

Faithfulness asks whether every claim in an answer is supported by the passages
the answer was built from. That needs an LLM judge, so the judging itself lives in
``scripts/chat_eval_faithfulness.py`` (optional, local, Ragas). This module is the
hermetic part: it turns a recorded ``/rest/v1/completion`` body into
``(question, answer, passages)``, decides which rows can be judged at all, and
summarises the judge's verdicts. No LLM and no network, so it runs in ``make test``.

Passages come from ``owasp_agent.data.evidence[].snippet``. The API caps each
snippet at ``SNIPPET_CAP`` characters, so a claim backed by text past the cap can
be judged unsupported. ``truncated_passages`` counts those snippets so a report
can say how much of the evidence the judge did not see.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence

from application.utils.ask_eval.gold import (
    ANSWER_LABEL_RE,
    GoldRow,
    normalize_completion,
)

# Length the staging API cuts evidence snippets to.
SNIPPET_CAP = 500
MARKER_RE = re.compile(r"\s*\[\d{1,2}\]")


@dataclass(frozen=True)
class FaithInput:
    id: str
    question: str
    answer: str
    passages: Sequence[str]
    truncated_passages: int


@dataclass(frozen=True)
class Statement:
    text: str
    supported: bool


@dataclass(frozen=True)
class FaithResult:
    id: str
    score: Optional[float]
    statements: Sequence[Statement] = field(default_factory=tuple)
    truncated_passages: int = 0
    n_passages: int = 0
    error: str = ""

    @property
    def unsupported(self) -> List[str]:
        return [s.text for s in self.statements if not s.supported]


# A judge takes (question, answer, passages) and returns its statement verdicts.
Judge = Callable[[str, str, Sequence[str]], Awaitable[Sequence[Statement]]]


def clean_answer(answer: str) -> str:
    """Drop the ``Answer:`` label and ``[n]`` markers so only claims are judged."""
    body = ANSWER_LABEL_RE.sub("", answer, count=1)
    return MARKER_RE.sub("", body).strip()


def evidence_passages(body: Mapping[str, Any]) -> List[str]:
    agent = body.get("owasp_agent") or {}
    data = agent.get("data") if isinstance(agent, Mapping) else None
    evidence = data.get("evidence") if isinstance(data, Mapping) else None
    out: List[str] = []
    for item in evidence or []:
        if isinstance(item, Mapping):
            text = str(item.get("snippet") or "").strip()
            if text:
                out.append(text)
    return out


def faithfulness_inputs(
    rows: Sequence[GoldRow], records: Sequence[Mapping[str, Any]]
) -> tuple[List[FaithInput], Dict[str, str]]:
    """Pick the rows a judge can score; say why each other row was skipped.

    Only ``expect: answer`` rows that came back 200, did not abstain, and carry
    passage text are judged. A refusal has no claims to check, and an answer with
    no passages cannot be checked against anything.
    """
    by_id = {str(r.get("id")): r for r in records}
    inputs: List[FaithInput] = []
    skipped: Dict[str, str] = {}
    for row in rows:
        if row.expect != "answer":
            skipped[row.id] = "refusal row"
            continue
        rec = by_id.get(row.id)
        if rec is None:
            skipped[row.id] = "no record"
            continue
        body = rec.get("body")
        if rec.get("status") != 200 or not isinstance(body, Mapping):
            skipped[row.id] = f"http {rec.get('status')}"
            continue
        if normalize_completion(body).abstained:
            skipped[row.id] = "answer abstained"
            continue
        passages = evidence_passages(body)
        if not passages:
            skipped[row.id] = "no passage text in response"
            continue
        inputs.append(
            FaithInput(
                id=row.id,
                question=row.question,
                answer=clean_answer(str(body.get("response") or "")),
                passages=passages,
                truncated_passages=sum(len(p) >= SNIPPET_CAP for p in passages),
            )
        )
    return inputs, skipped


async def judge_inputs(inputs: Sequence[FaithInput], judge: Judge) -> List[FaithResult]:
    """Run the judge over each input; one failed call does not stop the run."""
    results: List[FaithResult] = []
    for item in inputs:
        try:
            statements = tuple(await judge(item.question, item.answer, item.passages))
        except Exception as exc:  # judge is an external LLM; record and move on
            results.append(
                FaithResult(
                    id=item.id,
                    score=None,
                    truncated_passages=item.truncated_passages,
                    n_passages=len(item.passages),
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
            )
            continue
        score = (
            sum(s.supported for s in statements) / len(statements)
            if statements
            else None
        )
        results.append(
            FaithResult(
                id=item.id,
                score=score,
                statements=statements,
                truncated_passages=item.truncated_passages,
                n_passages=len(item.passages),
            )
        )
    return results


def summarize_faithfulness(results: Sequence[FaithResult]) -> Dict[str, Any]:
    scores: Dict[str, float] = {
        r.id: r.score
        for r in results
        if r.score is not None and not math.isnan(r.score)
    }
    judged = [r for r in results if r.id in scores]
    return {
        "judged": len(scores),
        "errors": {r.id: r.error for r in results if r.error},
        "mean_faithfulness": (
            round(sum(scores.values()) / len(scores), 3) if scores else None
        ),
        "statements": sum(len(r.statements) for r in judged),
        "supported_statements": sum(
            sum(s.supported for s in r.statements) for r in judged
        ),
        "fully_faithful": [i for i, s in scores.items() if s == 1.0],
        "below_one": {i: round(s, 3) for i, s in scores.items() if s < 1.0},
        "passages": sum(r.n_passages for r in results),
        "truncated_passages": sum(r.truncated_passages for r in results),
    }
