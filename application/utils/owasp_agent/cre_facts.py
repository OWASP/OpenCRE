"""Curated high-precision CRE factoids for deterministic Q&A (fail closed if unknown)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

# (match keywords in lowercase question) -> (cre_id, title, note)
CRE_FACTOIDS = [
    (
        ("output encoding", "xss"),
        "CRE-844-486",
        "Perform output encoding",
        "Primary CRE for encoding untrusted data before rendering to prevent XSS.",
    ),
    (
        ("output encoding",),
        "CRE-844-486",
        "Perform output encoding",
        "Primary CRE for encoding untrusted data before rendering to prevent XSS.",
    ),
]

# Explicit ids the agent can answer without keyword matching (still fail-closed
# for unknown ids — those return None and CRE RAG / caller decides).
CRE_BY_ID = {
    "cre-844-486": (
        "CRE-844-486",
        "Perform output encoding",
        "Primary CRE for encoding untrusted data before rendering to prevent XSS.",
    ),
}


def lookup_cre_factoid(question: str) -> Optional[Tuple[str, str, str]]:
    t = (question or "").lower()
    for m in re.finditer(r"\bcre[-\s]?(\d{3})[-\s]?(\d{3})\b", t):
        key = f"cre-{m.group(1)}-{m.group(2)}"
        hit = CRE_BY_ID.get(key)
        if hit:
            return hit
    if not re.search(r"\bcre\b|common requirements?", t):
        # still allow "which CRE covers" style
        if "which cre" not in t and "what cre" not in t:
            return None
    for keys, cre_id, title, note in CRE_FACTOIDS:
        if all(k in t for k in keys):
            return cre_id, title, note
    return None


def format_cre_factoid(cre_id: str, title: str, note: str) -> str:
    return (
        f'The CRE `{cre_id}` which is titled "{title}" covers this control. {note} '
        "Follow-up: I can list linked standards (ASVS/WSTG/Cheat Sheets) for this CRE "
        "if you want a citation table."
    )
