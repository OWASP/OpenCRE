"""Gold-set scoring for cited OpenCRE chat / ask answers (#1078).

Hermetic: no LLM judge and no network. A response is whatever ``/rest/v1/completion``
returned (``response``, ``table``, ``accurate``, ``owasp_agent.citations``), or the
same fields recorded to a fixture. Per case this scores:

- CRE recall: did any expected CRE id come back in the table or the citations.
- Cite groups: did each ``required_cite_groups`` family appear (``multicite``),
  e.g. SAMM must be cited when the question says "according to SAMM".
- Abstain: ``expect: abstain`` rows must abstain, ``expect: answer`` rows must not.
- Citation markers: every ``[n]`` in the answer points at a returned passage. This
  is the hermetic part of faithfulness; whether the cited passage actually supports
  the sentence needs an LLM judge (Ragas faithfulness) and is not scored here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from application.utils.ask_eval.multicite import missing_cite_groups
from application.utils.rag_parity.phase6_eval import GoldCase

CRE_ID_RE = re.compile(r"\b\d{3}-\d{3}\b")
MARKER_RE = re.compile(r"\[(\d{1,2})\]")
ABSTAIN_PREFIX = "I couldn't find that in the indexed OWASP sources"
# Staging's agent starts every reply with this label, refusals included.
ANSWER_LABEL_RE = re.compile(r"^\s*answer\s*:\s*", re.IGNORECASE)


@dataclass(frozen=True)
class GoldRow:
    id: str
    family: str
    question: str
    expect: str
    expected_cre_ids: Sequence[str] = ()
    required_cite_groups: Mapping[str, Sequence[str]] = field(default_factory=dict)
    must_contain_any: Sequence[str] = ()
    must_not_contain: Sequence[str] = ()
    reference: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    cre_ids: Sequence[str]
    cites: Sequence[str]
    n_passages: int
    abstained: bool


@dataclass(frozen=True)
class CaseScore:
    id: str
    expect: str
    abstain_ok: bool
    cre_hit: Optional[bool]
    missing_groups: Sequence[str]
    n_groups: int
    bad_markers: Sequence[int]
    contains_ok: bool
    # Share of returned CREs that the gold row lists. Reported, not part of
    # `passed`: gold rows list accepted CREs, not every correct sibling.
    cre_precision: Optional[float] = None

    @property
    def passed(self) -> bool:
        return (
            self.abstain_ok
            and self.cre_hit is not False
            and not self.missing_groups
            and not self.bad_markers
            and self.contains_ok
        )


def load_gold(path: Path) -> List[GoldRow]:
    rows: List[GoldRow] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        rows.append(
            GoldRow(
                id=str(raw["id"]),
                family=str(raw.get("family", "")),
                question=str(raw["question"]),
                expect=str(raw["expect"]),
                expected_cre_ids=tuple(raw.get("expected_cre_ids") or ()),
                required_cite_groups=dict(raw.get("required_cite_groups") or {}),
                must_contain_any=tuple(raw.get("must_contain_any") or ()),
                must_not_contain=tuple(raw.get("must_not_contain") or ()),
                reference=str(raw.get("reference", "")),
                notes=str(raw.get("notes", "")),
            )
        )
    return rows


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def normalize_completion(payload: Mapping[str, Any]) -> ChatResponse:
    """Turn a ``/rest/v1/completion`` JSON body into what the scorer reads."""
    answer = str(payload.get("response") or "")
    table = payload.get("table") or []
    if not isinstance(table, list):
        table = []
    agent = payload.get("owasp_agent") or {}
    agent_cites = agent.get("citations") if isinstance(agent, Mapping) else None
    cites: List[str] = []
    for row in table:
        cites.extend(_strings(row))
    cites.extend(_strings(agent_cites or []))
    cre_ids: List[str] = []
    for text in cites:
        for cid in CRE_ID_RE.findall(text):
            if cid not in cre_ids:
                cre_ids.append(cid)
    body = ANSWER_LABEL_RE.sub("", answer, count=1)
    abstained = not payload.get("accurate") or body.startswith(ABSTAIN_PREFIX)
    # [n] points into the agent's citation list when there is one (staging),
    # otherwise into the passages in ``table`` (generate_text path).
    n_passages = len(agent_cites) if agent_cites else len(table)
    return ChatResponse(
        answer=answer,
        cre_ids=cre_ids,
        cites=cites,
        n_passages=n_passages,
        abstained=abstained,
    )


def score_case(row: GoldRow, resp: ChatResponse) -> CaseScore:
    if row.expect == "abstain":
        return CaseScore(
            id=row.id,
            expect=row.expect,
            abstain_ok=resp.abstained,
            cre_hit=None,
            missing_groups=(),
            n_groups=0,
            bad_markers=(),
            contains_ok=True,
        )
    cre_hit: Optional[bool] = None
    cre_precision: Optional[float] = None
    if row.expected_cre_ids:
        got = set(resp.cre_ids)
        found = set(row.expected_cre_ids) & got
        cre_hit = bool(found)
        if got:
            cre_precision = len(found) / len(got)
    markers = sorted({int(m) for m in MARKER_RE.findall(resp.answer)})
    bad = [m for m in markers if m < 1 or m > resp.n_passages]
    low = resp.answer.lower()
    contains_ok = (
        not row.must_contain_any or any(s.lower() in low for s in row.must_contain_any)
    ) and not any(s.lower() in low for s in row.must_not_contain)
    return CaseScore(
        id=row.id,
        expect=row.expect,
        abstain_ok=not resp.abstained,
        cre_hit=cre_hit,
        missing_groups=missing_cite_groups(resp.cites, row.required_cite_groups),
        n_groups=len(row.required_cite_groups),
        bad_markers=bad,
        contains_ok=contains_ok,
        cre_precision=cre_precision,
    )


def summarize(scores: Sequence[CaseScore]) -> Dict[str, Any]:
    answer = [s for s in scores if s.expect == "answer"]
    abstain = [s for s in scores if s.expect == "abstain"]
    with_cre = [s for s in answer if s.cre_hit is not None]
    grouped = [s for s in answer if s.n_groups]
    precisions = [s.cre_precision for s in answer if s.cre_precision is not None]

    def rate(hits: int, n: int) -> Optional[float]:
        return round(hits / n, 3) if n else None

    return {
        "n": len(scores),
        "passed": sum(s.passed for s in scores),
        "cre_recall": rate(sum(bool(s.cre_hit) for s in with_cre), len(with_cre)),
        "cre_precision": (
            round(sum(precisions) / len(precisions), 3) if precisions else None
        ),
        "cite_group_recall": rate(
            sum(not s.missing_groups for s in grouped), len(grouped)
        ),
        "abstain_correct": rate(sum(s.abstain_ok for s in abstain), len(abstain)),
        "false_abstain": rate(sum(not s.abstain_ok for s in answer), len(answer)),
        "bad_marker_cases": [s.id for s in answer if s.bad_markers],
        "failed": [s.id for s in scores if not s.passed],
    }


def to_phase6_cases(rows: Sequence[GoldRow]) -> List[GoldCase]:
    """Bridge to ``phase6_eval`` so ``neighbourhood_hit_at_k`` runs on real gold."""
    return [
        GoldCase(query=r.question, expected_cre_ids=list(r.expected_cre_ids))
        for r in rows
        if r.expect == "answer" and r.expected_cre_ids
    ]
