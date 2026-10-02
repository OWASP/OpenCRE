"""OWASP Agent — experimental OIE chat extension for community/metadata Q&A.

This channel is intentionally separate from Module C (Librarian → CRE).
Logistics and governance metadata must not be forced through CRE mapping.
"""

from __future__ import annotations

from application.utils.owasp_agent.router import (
    OwaspAgentRouter,
    is_owasp_agent_enabled,
)

__all__ = [
    "OwaspAgentRouter",
    "is_owasp_agent_enabled",
]
