"""Prepend Standard/Section metadata when missing before embed/retrieve.

Many B2 chunks already carry ``Standard:`` / ``Section:`` headers that dual-index
splits on. Enrich only when those lines are absent so we do not double-prefix.
"""

from __future__ import annotations

import re
from typing import Optional

_STANDARD_LINE = re.compile(r"(?im)^Standard:\s*(.+)$")
_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_SOURCE_LINE = re.compile(r"(?im)^Source:\s*(.+)$")


def _has_standard(text: str) -> bool:
    return bool(_STANDARD_LINE.search(text or ""))


def _has_section(text: str) -> bool:
    return bool(_SECTION_LINE.search(text or ""))


def enrich_query_context(
    text: str,
    *,
    standard: str = "",
    section: str = "",
    title_hint: Optional[str] = None,
) -> str:
    """Return ``text`` with missing Standard/Section lines prepended.

    Prefer explicit ``standard`` / ``section``; fall back to ``title_hint`` for
    Section and ``Source:`` stem for Standard when those headers are missing.
    Already-complete texts are returned unchanged.
    """
    body = text or ""
    need_standard = not _has_standard(body)
    need_section = not _has_section(body)
    if not need_standard and not need_section:
        return body

    std = (standard or "").strip()
    sec = (section or "").strip()
    if need_standard and not std:
        src = _SOURCE_LINE.search(body)
        if src:
            # Source is often a filename (A01.txt); keep as a weak Standard hint.
            std = src.group(1).strip()
    if need_section and not sec:
        sec = (title_hint or "").strip()

    prefix_lines = []
    if need_standard and std:
        prefix_lines.append(f"Standard: {std}")
    if need_section and sec:
        prefix_lines.append(f"Section: {sec}")
    if not prefix_lines:
        return body

    # Bracket form matches the peer proposal; line form keeps dual-index split.
    # Prefer line headers so focus_query / dual-index keep working.
    header = "\n".join(prefix_lines)
    if body.strip():
        return f"{header}\n\n{body.lstrip()}"
    return header


__all__ = ["enrich_query_context"]
