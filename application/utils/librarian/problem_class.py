"""Module C.0.4 — rule-based problem-class classifier.

Turns section text (ideally with ``Standard:`` / ``Section-ID:`` / ``Section:``
prefixes from Module A) into a problem class + family. Prefer exact Section-ID
lookups from Node ``document_metadata.oie`` (via ``TaxonomyIndex``); fall back to
title/body phrases and standard hints also loaded from that index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from application.utils.librarian.oie_taxonomy import (
    TaxonomyIndex,
    get_default_taxonomy_index,
)


@dataclass(frozen=True)
class ProblemClass:
    """Security problem class for one chunk."""

    class_id: str
    family: str
    evidence: str = ""
    section_id: str = ""
    standard: str = ""


_SECTION_ID_LINE = re.compile(r"(?im)^Section-ID:\s*(.+)$")
_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_STANDARD_LINE = re.compile(r"(?im)^Standard:\s*(.+)$")
_SOURCE_LINE = re.compile(r"(?im)^Source:\s*(.+)$")
# Prefer known catalog tokens; ASVS-style V1.2.3 is kept but not mapped by Node oie.
# Delimit by non-alnum so Source paths like ``A05_Injection.md`` still match.
_ID_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS\d{1,2})(?![A-Za-z0-9])",
    re.I,
)


def _parse_prefix_ids(text: str) -> List[str]:
    """Prefer Source filename ids; Section-ID line is nav-polluted on OWASP HTML.

    Source stem (``A05.txt``, ``API7.md``) is authoritative. Only when Source
    has no catalog token do we take the **first** id on the Section-ID line
    (never the full comma-separated nav list).
    """
    src = _SOURCE_LINE.search(text or "")
    if src:
        src_ids: List[str] = []
        for tok in _ID_TOKEN.findall(src.group(1)):
            sid = tok.upper()
            if sid not in src_ids:
                src_ids.append(sid)
        if src_ids:
            return src_ids

    m = _SECTION_ID_LINE.search(text or "")
    if m:
        toks = _ID_TOKEN.findall(m.group(1))
        if toks:
            return [toks[0].upper()]
    return []


def classify_problem(text: str, index: Optional[TaxonomyIndex] = None) -> ProblemClass:
    """Classify one section's text into a problem class + family.

    Order: exact Section-ID → title phrases → title+short body phrases →
    standard→family default. Unknown → ``general`` / ``appsec``.
    """
    idx = index if index is not None else get_default_taxonomy_index()
    text = text or ""
    standard_m = _STANDARD_LINE.search(text)
    standard = standard_m.group(1).strip() if standard_m else ""
    section_m = _SECTION_LINE.search(text)
    section_title = section_m.group(1).strip() if section_m else ""

    for sid in _parse_prefix_ids(text):
        hit = idx.lookup_section_id(sid)
        if hit:
            class_id, family = hit
            return ProblemClass(
                class_id,
                family,
                evidence=f"section_id:{sid}",
                section_id=sid,
                standard=standard,
            )

    # Title only first (stricter), then title + first ~800 chars of body.
    title_hit = idx.match_phrases(section_title)
    if title_hit:
        class_id, family = title_hit
        return ProblemClass(
            class_id,
            family,
            evidence="keyword:title",
            section_id="",
            standard=standard,
        )

    body_head = text[:800]
    # Strip metadata lines so Source/Standard tokens do not drive keywords.
    body_lines = [
        ln
        for ln in body_head.splitlines()
        if not re.match(r"^(Standard|Source|Section-ID|Section|Version):", ln, re.I)
    ]
    blob = " ".join([section_title, " ".join(body_lines)])
    kw = idx.match_phrases(blob)
    if kw:
        class_id, family = kw
        return ProblemClass(
            class_id,
            family,
            evidence="keyword:body",
            section_id="",
            standard=standard,
        )

    fam = idx.family_for_standard(standard) or "appsec"
    return ProblemClass(
        "general",
        fam,
        evidence=f"standard:{standard or 'unknown'}",
        section_id="",
        standard=standard,
    )


def classify_problems(
    texts: Iterable[str], index: Optional[TaxonomyIndex] = None
) -> List[ProblemClass]:
    return [classify_problem(t, index=index) for t in texts]


__all__ = ["ProblemClass", "classify_problem", "classify_problems"]
