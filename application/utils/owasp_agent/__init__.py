"""OWASP Agent — experimental OIE chat/MCP extension for community metadata Q&A.

Isolation contract
------------------
* Meta entities live in the agent index (``OWASP_AGENT_DB`` / app Postgres
  ``meta_*`` tables) — never as CRE graph nodes.
* May write ``embeddings`` rows only with
  ``source_channel='owasp_agent_meta'`` (multi-lane chat routing). Never create
  Credoctypes / Node / CRE graph links from this package.
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
