"""Curated OWASP AI Exchange factoids (deterministic Q&A with citations)."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# (match predicates on lowercase question) -> (message, citations)
AIX_FACTOIDS: List[Tuple[Tuple[str, ...], str, List[str]]] = [
    (
        ("lethal trifecta",),
        (
            "According to the OWASP AI Exchange, for leaking sensitive data in "
            "agentic AI you need three things together (the lethal trifecta): "
            "(1) attacker-influenced data that reaches the model (often via "
            "indirect prompt injection), (2) access of that model or connected "
            "agents to sensitive data, and (3) the ability to send data out to "
            "an attacker. The impact is data exfiltration. Removing any one leg "
            "blocks the attack path."
        ),
        ["https://owaspai.org/docs/ai_security_overview/"],
    ),
]


def lookup_aix_factoid(question: str) -> Optional[Tuple[str, List[str]]]:
    t = (question or "").lower()
    if not t:
        return None
    # Prefer AIX-attributed or explicit trifecta asks.
    aix_hint = bool(
        re.search(r"\b(ai exchange|owaspai|aix)\b", t) or "lethal trifecta" in t
    )
    if not aix_hint:
        return None
    for keys, message, citations in AIX_FACTOIDS:
        if all(k in t for k in keys):
            return message, list(citations)
    return None
