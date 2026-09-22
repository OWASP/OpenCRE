"""Compact query text for C.2: metadata + section title only.

Used as a cheap first-pass CE query. On a miss (low calibrated confidence),
the pipeline retries with the full narrative chunk.
"""

from __future__ import annotations

import re
from typing import List

_META = re.compile(
    r"^(Standard|Version|Source|Section-ID|Section)\s*:",
    re.I,
)


def focus_query_text(text: str) -> str:
    """Keep Standard/Version/Source/Section-ID/Section lines (+ blank).

    Drops the narrative body so CE/title ranking is not drowned by long HTML
    residue. Empty if no metadata lines exist (caller should use full text).
    """
    lines: List[str] = []
    for ln in (text or "").splitlines():
        if _META.match(ln.strip()):
            lines.append(ln.strip())
    if not lines:
        return ""
    return "\n".join(lines)


def body_query_text(text: str) -> str:
    """Narrative only — drop Standard/Version/Source/Section-ID/Section lines."""
    lines: List[str] = []
    for ln in (text or "").splitlines():
        if _META.match(ln.strip()):
            continue
        lines.append(ln)
    return "\n".join(lines).strip()


def split_retrieval_query(text: str) -> tuple[str, str]:
    """Header titles vs body. Length is not the split — metadata lines are."""
    return focus_query_text(text), body_query_text(text)


__all__ = ["body_query_text", "focus_query_text", "split_retrieval_query"]
