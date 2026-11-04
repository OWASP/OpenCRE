"""Phase 6: Ragas / DeepEval runners bridged to OpenCRE gold metrics.

Not on the default ``make test`` paid path — invoke via Makefile target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class GoldCase:
    query: str
    expected_cre_ids: Sequence[str]
    answer: str = ""
    contexts: Sequence[str] = ()


@dataclass(frozen=True)
class EvalReport:
    framework: str
    n: int
    hit_at_k: float
    notes: str = ""


RetrieverFn = Callable[[str], Sequence[str]]


def neighbourhood_hit_at_k(
    cases: Sequence[GoldCase],
    retrieve: RetrieverFn,
    *,
    k: int = 5,
) -> float:
    """Bridge to existing gold: fraction of cases with any expected id in top-k."""
    if not cases:
        return 0.0
    hits = 0
    for case in cases:
        got = list(retrieve(case.query))[:k]
        expected = set(case.expected_cre_ids)
        if expected.intersection(got):
            hits += 1
    return hits / float(len(cases))


def run_ragas_bridge(
    cases: Sequence[GoldCase],
    retrieve: RetrieverFn,
    *,
    k: int = 5,
) -> EvalReport:
    """Prefer Ragas if installed; always compute neighbourhood hit@k bridge."""
    hit = neighbourhood_hit_at_k(cases, retrieve, k=k)
    notes = "ragas_optional_unavailable"
    try:
        import ragas  # type: ignore  # noqa: F401

        notes = "ragas_imported; neighbourhood_hit used as bridge metric"
    except Exception:  # noqa: BLE001
        pass
    return EvalReport(framework="ragas_bridge", n=len(cases), hit_at_k=hit, notes=notes)


def run_deepeval_bridge(
    cases: Sequence[GoldCase],
    retrieve: RetrieverFn,
    *,
    k: int = 5,
) -> EvalReport:
    hit = neighbourhood_hit_at_k(cases, retrieve, k=k)
    notes = "deepeval_optional_unavailable"
    try:
        import deepeval  # type: ignore  # noqa: F401

        notes = "deepeval_imported; neighbourhood_hit used as bridge metric"
    except Exception:  # noqa: BLE001
        pass
    return EvalReport(
        framework="deepeval_bridge", n=len(cases), hit_at_k=hit, notes=notes
    )


def reports_to_dict(reports: Sequence[EvalReport]) -> List[Dict[str, object]]:
    return [
        {
            "framework": r.framework,
            "n": r.n,
            "hit_at_k": r.hit_at_k,
            "notes": r.notes,
        }
        for r in reports
    ]
