"""Experimental thin-retrieval fail-closed gate.

Gated by ``CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED`` (default off). When the
retrieval shortlist is empty, shorter than ``CRE_LIBRARIAN_COVERAGE_MIN_CANDIDATES``
(default 2), or the best ``score_vector`` is below
``CRE_LIBRARIAN_COVERAGE_MIN_SCORE`` (default 0.05), force review with
``COVERAGE_THIN`` instead of auto-linking.
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

from application.utils.librarian.schemas import CreCandidate


def coverage_fail_closed_enabled() -> bool:
    return os.environ.get(
        "CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED", "0"
    ).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _min_candidates() -> int:
    raw = os.environ.get("CRE_LIBRARIAN_COVERAGE_MIN_CANDIDATES", "2")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 2


def _min_score() -> float:
    raw = os.environ.get("CRE_LIBRARIAN_COVERAGE_MIN_SCORE", "0.05")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.05


def coverage_is_thin(candidates: Sequence[CreCandidate]) -> bool:
    """True when the shortlist is too weak to auto-link."""
    if not coverage_fail_closed_enabled():
        return False
    rows = list(candidates or [])
    if len(rows) < _min_candidates():
        return True
    best: Optional[float] = None
    for c in rows:
        score = getattr(c, "score_vector", None)
        if score is None:
            continue
        try:
            val = float(score)
        except (TypeError, ValueError):
            continue
        if best is None or val > best:
            best = val
    if best is None:
        return True
    return best < _min_score()
