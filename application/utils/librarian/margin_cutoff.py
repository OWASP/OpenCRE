"""Relative score-margin cutoff for decision shortlists.

Always keep rank-1. Keep candidate i>1 only if
``score_i >= gamma * score_1``. Distinct from ``CRE_LIBRARIAN_HYBRID_GAMMA``
(CE mix weight in C.2).
"""

from __future__ import annotations

from typing import List, Sequence

from application.utils.librarian.schemas import CreCandidate


def _candidate_score(candidate: CreCandidate) -> float:
    for attr in ("score_rerank", "score_hybrid", "score_vector"):
        val = getattr(candidate, attr, None)
        if val is not None:
            return float(val)
    return 0.0


def apply_margin_gamma(
    candidates: Sequence[CreCandidate],
    *,
    gamma: float,
) -> List[CreCandidate]:
    """Filter an ordered shortlist by relative margin to rank-1."""
    if not candidates:
        return []
    if gamma <= 0:
        return list(candidates)
    first = candidates[0]
    score_1 = _candidate_score(first)
    if score_1 <= 0:
        return [first]
    floor = gamma * score_1
    kept: List[CreCandidate] = [first]
    for candidate in candidates[1:]:
        if _candidate_score(candidate) >= floor:
            kept.append(candidate)
    return kept


def apply_margin_gamma_ids(
    cre_ids: Sequence[str],
    scores_by_id: dict[str, float],
    *,
    gamma: float,
) -> List[str]:
    """Same margin rule over an ordered id list + score map."""
    if not cre_ids:
        return []
    if gamma <= 0:
        return list(cre_ids)
    first = cre_ids[0]
    score_1 = float(scores_by_id.get(first, 0.0))
    if score_1 <= 0:
        return [first]
    floor = gamma * score_1
    kept: List[str] = [first]
    for cid in cre_ids[1:]:
        if float(scores_by_id.get(cid, 0.0)) >= floor:
            kept.append(cid)
    return kept


__all__ = ["apply_margin_gamma", "apply_margin_gamma_ids"]
