"""Lexical title ↔ CRE name/text boost + hybrid ranking helpers for C.2."""

from __future__ import annotations

import re
from typing import List, Sequence, Set

_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_TOKEN = re.compile(r"[a-z0-9]{3,}")
_STOP: Set[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "owasp",
        "top",
        "broken",
        "failure",
        "failures",
        "security",
        "application",
        "section",
        "standard",
        "source",
    }
)


def section_title_tokens(text: str) -> Set[str]:
    """Tokens from ``Section:`` line, else first non-meta line."""
    m = _SECTION_LINE.search(text or "")
    title = m.group(1).strip() if m else ""
    if not title:
        for line in (text or "").splitlines():
            s = line.strip()
            if not s or re.match(r"^(Standard|Source|Section-ID|Section):", s, re.I):
                continue
            title = s
            break
    return {t for t in _TOKEN.findall(title.lower()) if t not in _STOP}


def title_overlap_boost(
    query_text: str, cre_blob: str, *, weight: float = 1.0
) -> float:
    """Return ``weight * |title ∩ cre| / |title|`` (0 when no title tokens)."""
    q = section_title_tokens(query_text)
    if not q:
        return 0.0
    c = set(_TOKEN.findall((cre_blob or "").lower()))
    return weight * (len(q & c) / len(q))


def apply_title_boost(
    query_text: str,
    scores: Sequence[float],
    cre_blobs: Sequence[str],
    *,
    weight: float = 2.0,
) -> List[float]:
    """Add title overlap boost to each score (same order as ``cre_blobs``)."""
    out: List[float] = []
    for score, blob in zip(scores, cre_blobs, strict=True):
        out.append(float(score) + title_overlap_boost(query_text, blob, weight=weight))
    return out


def _minmax(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def hybrid_rank_scores(
    *,
    vectors: Sequence[float],
    ce_scores: Sequence[float],
    title_boosts: Sequence[float],
    alpha: float,
    beta: float,
    gamma: float,
) -> List[float]:
    """``α·vector + β·title + γ·minmax(CE)`` — higher is better."""
    n = len(vectors)
    if not (len(ce_scores) == len(title_boosts) == n):
        raise ValueError("vectors, ce_scores, and title_boosts must align")
    ce_n = _minmax([float(s) for s in ce_scores])
    out: List[float] = []
    for i in range(n):
        out.append(
            alpha * float(vectors[i]) + beta * float(title_boosts[i]) + gamma * ce_n[i]
        )
    return out


__all__ = [
    "apply_title_boost",
    "hybrid_rank_scores",
    "section_title_tokens",
    "title_overlap_boost",
]
