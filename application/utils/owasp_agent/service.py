"""One entry point for "answer this OWASP question", shared by the web chatbot and MCP ``ask``.

Both call :func:`route_question`, so routing, the answer pipeline, error handling and the
evidence returned are the same. The only caller-specific input is ``history`` (the web chat
keeps conversation memory; MCP callers may pass it too).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OwaspAgentUnavailable(Exception):
    """The OWASP agent failed on a question that must not fall through to CRE retrieval."""


def route_question(
    prompt: str, history: Optional[List[Dict[str, str]]] = None
) -> Optional[Dict[str, Any]]:
    """The OWASP agent's response for ``prompt``, or ``None`` when it does not handle it.

    Raises :class:`OwaspAgentUnavailable` when the agent crashes on a community/meta question
    (we must not answer those from CRE retrieval); a crash on a CRE-shaped question returns
    ``None`` so the caller can use the CRE path.
    """
    from application.utils.owasp_agent import OwaspAgentRouter, is_owasp_agent_enabled

    if not is_owasp_agent_enabled():
        return None
    try:
        return OwaspAgentRouter().handle(prompt or "", history=history or None)
    except Exception:  # noqa: BLE001
        logger.exception("owasp agent router failed")
        try:
            from application.utils.owasp_agent.router import classify_intent

            if classify_intent(prompt or "") != "cre_normative":
                raise OwaspAgentUnavailable() from None
        except OwaspAgentUnavailable:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("owasp agent classify_intent also failed")
            raise OwaspAgentUnavailable() from None
        return None
