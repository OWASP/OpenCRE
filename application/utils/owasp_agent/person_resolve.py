"""Resolve person mentions from the local index (no CapWords name invention)."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from application.utils.owasp_agent.index_store import IndexStore


def list_indexed_person_names(store: IndexStore) -> List[str]:
    """All person names known to the meta index, longest-first for substring match."""
    seen: set[str] = set()
    names: List[str] = []

    def _add(raw: object) -> None:
        n = str(raw or "").strip()
        if len(n) < 4:
            return
        key = n.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(n)

    for kind in (
        "project_leader",
        "board_member",
        "board_candidate",
        "person",
        "board_roster",
    ):
        for row in store.list_entities(kind):
            if not isinstance(row, dict):
                continue
            _add(row.get("name"))
            for leader in row.get("leaders") or []:
                _add(leader)
            for member in row.get("members") or []:
                if isinstance(member, dict):
                    _add(member.get("name"))
                else:
                    _add(member)
            for cand in row.get("candidates") or []:
                if isinstance(cand, dict):
                    _add(cand.get("name"))
                else:
                    _add(cand)

    for kind in ("project", "chapter"):
        for row in store.list_entities(kind):
            if not isinstance(row, dict):
                continue
            for leader in row.get("leaders") or []:
                _add(leader)

    names.sort(key=lambda s: len(s), reverse=True)
    return names


def match_indexed_person(
    text: str, names: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Return the longest indexed name appearing in ``text``, or a quoted span."""
    if not text:
        return None
    m = re.search(r"[\"']([^\"']{3,80})[\"']", text)
    if m:
        quoted = m.group(1).strip()
        if names:
            ql = quoted.lower()
            for n in names:
                nl = n.lower()
                if nl == ql or nl in ql or ql in nl:
                    return n
        return quoted

    if names:
        t = text.lower()
        for n in names:
            nl = n.lower()
            if nl and nl in t:
                return n

    # Minimal structural cues only (not a CapWords forest) for fail-closed
    # answers about people not yet in the index.
    return _person_structural_span(text)


def _person_structural_span(text: str) -> Optional[str]:
    """Few fixed frames: Who is X / Is X on / Show X's / Name: … / Name — …"""
    patterns = (
        r"\b[Ww]ho\s+is\s+([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)"
        r"(?:\s+at\s+OWASP)?\s*\??",
        r"\b[Ii]s\s+([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)\s+on\b",
        r"\b[Ss]how\s+([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)(?:'s|’s)\b",
        r"^([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)\s*:",
        r"^([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)\s*[—–\-]\s*",
        r"\b[Dd]id\s+([A-Z][A-Za-z]+(?:\s+(?:van|der|de|la|von|[A-Z][A-Za-z]+))+)\s+"
        r"(?:run|ever|say|give|present)\b",
    )
    for pat in patterns:
        m = re.search(pat, text.strip())
        if m:
            return m.group(1).strip().rstrip(".?!")
    return None
