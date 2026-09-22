"""Optional requirement matcher / extractor for Module A.

When enabled (``ChunkingConfig.requirement_extract``), documents that look like
control catalogs (ASVS-style tables, NIST/ISO ids) are split into one chunk per
requirement. Narrative docs (cheat sheets, prose) are left alone under ``auto``.

This is separate from A.2 ``merge_profile=requirements`` (merge fence). Extraction
produces requirement-grain *inputs*; the merger only avoids gluing different ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from application.utils.harvester.models import ChunkInfo
from application.utils.harvester.requirement_ids import requirement_ids

# Table row: | **1.1.2** | Verify that … | 2 |
_TABLE_REQ_ROW_RE = re.compile(
    r"^\|\s*\*?\*?V?(\d+\.\d+\.\d+)\*?\*?\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE | re.IGNORECASE,
)
# Standalone heading-ish: ### V1.1.2 or **1.1.2** at line start
_LINE_REQ_RE = re.compile(
    r"^(?:#{1,6}\s*)?\*?\*?V?(\d+\.\d+\.\d+)\*?\*?\b[^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)
_VERIFY_RE = re.compile(r"\bVerify that\b", re.IGNORECASE)

# Auto gate: enough distinct 3-part decimal ids, or table rows + verify language.
_AUTO_MIN_DISTINCT_IDS = 5
_AUTO_MIN_TABLE_ROWS = 3


@dataclass(frozen=True)
class RequirementSegment:
    """One extracted requirement with source offsets into the parent document."""

    requirement_id: str  # canonical display id, e.g. V1.1.2 or AC-2
    text: str
    start_char_idx: int
    end_char_idx: int


def normalize_asvs_id(raw: str) -> str:
    """Map ``1.1.2`` / ``v1.1.2`` → ``V1.1.2``; leave other families unchanged."""
    s = (raw or "").strip()
    if re.fullmatch(r"V?\d+\.\d+\.\d+", s, flags=re.IGNORECASE):
        return "V" + s.lstrip("Vv")
    return s


def requirements_needed(text: str) -> bool:
    """Return True when the document looks like a requirement catalog.

    Heuristic only — used by ``requirement_extract=auto``. Prefer explicit
    ``on`` / ``off`` in repo YAML when the answer is known.
    """
    body = text or ""
    if len(body) < 80:
        return False

    table_rows = list(_TABLE_REQ_ROW_RE.finditer(body))
    if len(table_rows) >= _AUTO_MIN_TABLE_ROWS:
        return True

    decimal_three = {
        m.group(1)
        for m in re.finditer(r"(?<![\w.])V?(\d+\.\d+\.\d+)(?![\d.])", body, re.I)
    }
    if len(decimal_three) >= _AUTO_MIN_DISTINCT_IDS and _VERIFY_RE.search(body):
        return True

    # NIST / ISO dense catalogs (ids without ASVS tables).
    ids = requirement_ids(body)
    nist_iso = {i for i in ids if "-" in i or i.startswith("a.")}
    if len(nist_iso) >= _AUTO_MIN_DISTINCT_IDS:
        return True

    return False


def extract_requirement_segments(text: str) -> List[RequirementSegment]:
    """Extract requirement-scoped segments from ``text``.

    Prefers markdown table rows (``| **1.1.2** | … |``). Falls back to
    line-anchored ids. Returns [] when nothing usable is found (caller keeps
    normal chunking).
    """
    body = text or ""
    if not body.strip():
        return []

    table = _segments_from_table_rows(body)
    if table:
        return table
    return _segments_from_line_ids(body)


def extract_requirement_chunks(text: str) -> List[ChunkInfo]:
    """Build ``ChunkInfo`` list with B2-style Section-ID prefixes."""
    out: List[ChunkInfo] = []
    for seg in extract_requirement_segments(text):
        prefixed = (
            f"Source: {seg.requirement_id}\n"
            f"Section-ID: {seg.requirement_id}\n"
            f"Section: {seg.text.splitlines()[0][:200] if seg.text else seg.requirement_id}\n\n"
            f"{seg.text}"
        )
        # Prefix is synthetic — keep offsets pointing at the original span so
        # validators that check idx ordering still see start < end on body.
        out.append(
            ChunkInfo(
                text=prefixed,
                start_char_idx=seg.start_char_idx,
                end_char_idx=max(seg.end_char_idx, seg.start_char_idx + 1),
            )
        )
    return out


def should_extract_requirements(
    text: str,
    *,
    mode: str,
) -> bool:
    """Resolve ``off`` / ``auto`` / ``on`` against document text."""
    m = (mode or "off").strip().lower()
    if m in ("0", "false", "no", "off", "none"):
        return False
    if m in ("1", "true", "yes", "on", "always"):
        return True
    if m == "auto":
        return requirements_needed(text)
    return False


def _segments_from_table_rows(body: str) -> List[RequirementSegment]:
    matches = list(_TABLE_REQ_ROW_RE.finditer(body))
    if len(matches) < 2:
        return []
    segs: List[RequirementSegment] = []
    for i, match in enumerate(matches):
        rid = normalize_asvs_id(match.group(1))
        desc = match.group(2).strip()
        start = match.start()
        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else _paragraph_end(body, match.end())
        )
        snippet = body[start:end].strip()
        if not snippet:
            snippet = f"{rid} {desc}".strip()
        segs.append(
            RequirementSegment(
                requirement_id=rid,
                text=snippet,
                start_char_idx=start,
                end_char_idx=end,
            )
        )
    return segs


def _segments_from_line_ids(body: str) -> List[RequirementSegment]:
    matches = list(_LINE_REQ_RE.finditer(body))
    # Need several anchors or we risk chopping narrative headings.
    if len(matches) < 2:
        return []
    segs: List[RequirementSegment] = []
    for i, match in enumerate(matches):
        rid = normalize_asvs_id(match.group(1))
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        snippet = body[start:end].strip()
        if len(snippet) < 40:
            continue
        segs.append(
            RequirementSegment(
                requirement_id=rid,
                text=snippet,
                start_char_idx=start,
                end_char_idx=end,
            )
        )
    return segs


def _paragraph_end(body: str, from_idx: int) -> int:
    """End of current table block or next blank line after ``from_idx``."""
    rest = body[from_idx:]
    # Prefer end of contiguous table lines.
    lines = rest.splitlines(keepends=True)
    offset = from_idx
    for line in lines:
        if line.startswith("|") or not line.strip():
            offset += len(line)
            if not line.strip() and offset > from_idx + 1:
                return offset
            continue
        break
    return min(len(body), max(from_idx + 1, offset))


__all__ = [
    "RequirementSegment",
    "extract_requirement_chunks",
    "extract_requirement_segments",
    "normalize_asvs_id",
    "requirements_needed",
    "should_extract_requirements",
]
