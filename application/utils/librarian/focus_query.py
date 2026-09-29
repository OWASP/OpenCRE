"""Compact query text for C.2 / dual-index: metadata vs narrative.

Used as a cheap first-pass CE query. On a miss (low calibrated confidence),
the pipeline retries with the full narrative chunk.

Dual-index name packing uses **title lines only** (Source/Section/Section-ID).
``Standard:`` / ``Version:`` stay on the chunk for hub-link year scope and
edition remap, but must not enter the CRE-name embedding query — otherwise
every catalog's name retrieve drifts when version headers are added.
"""

from __future__ import annotations

import re
from typing import List

_META = re.compile(
    r"^(Standard|Version|Source|Section-ID|Section)\s*:",
    re.I,
)
# Name-pool / dual-index header: section identity only (no Standard/Version).
_NAME_PACK = re.compile(
    r"^(Source|Section-ID|Section)\s*:",
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


def name_pack_query_text(text: str) -> str:
    """Section title / id lines only — for dual-index CRE-name retrieval.

    Omits ``Standard:`` / ``Version:`` so year labels do not contaminate the
    name embedding while remaining available on the full chunk for hub seed.
    """
    lines: List[str] = []
    for ln in (text or "").splitlines():
        if _NAME_PACK.match(ln.strip()):
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
    """Name-pack header vs body. Length is not the split — metadata lines are."""
    return name_pack_query_text(text), body_query_text(text)


__all__ = [
    "body_query_text",
    "focus_query_text",
    "name_pack_query_text",
    "split_retrieval_query",
]
