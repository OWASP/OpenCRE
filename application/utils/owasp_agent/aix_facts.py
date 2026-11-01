"""Curated OWASP AI Exchange evidence text (seeded into meta embeddings).

Runtime answers come from similarity retrieve of evidence rows — not keyword dumps.
"""

from __future__ import annotations

from typing import List, Tuple

# (topic keys for embedding Topics line) -> (message, citations)
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
