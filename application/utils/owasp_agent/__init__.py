"""OWASP Agent — experimental OIE chat/MCP extension for community metadata Q&A.

Isolation contract
------------------
* Data lives only in the separate ``OWASP_AGENT_DB`` SQLite index.
* Never write Credoctypes / Node / CRE / standard embeddings from this package.
* Never expose entities via CRE REST (tags, text_search, standards, graph UI).
* Reachable only from:
  1. Chat RAG router (``/rest/v1/completion`` when ``OWASP_AGENT_ENABLED``)
  2. MCP local tools ``owasp_meta_*`` (same flag)
"""

from __future__ import annotations

from application.utils.owasp_agent.router import (
    OwaspAgentRouter,
    is_owasp_agent_enabled,
)

# Presentation channel marker for chat/MCP clients.
PRESENTATION_CHANNEL = "chat_and_mcp_only"

__all__ = [
    "OwaspAgentRouter",
    "PRESENTATION_CHANNEL",
    "is_owasp_agent_enabled",
]
