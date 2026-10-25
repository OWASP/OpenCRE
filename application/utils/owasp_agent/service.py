"""One entry point for "answer this OWASP question", shared by the web chatbot and MCP ``ask``.

Both call :func:`route_question`, so routing, the answer pipeline, error handling and the
evidence returned are the same. The only caller-specific input is ``history`` (the web chat
keeps conversation memory; MCP callers may pass it too).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OwaspAgentUnavailable(Exception):
    """The OWASP agent failed on a question that must not fall through to CRE retrieval."""


def _cre_attach_threshold() -> float:
    try:
        return float(os.environ.get("OWASP_CRE_ATTACH_THRESHOLD", "0.6"))
    except ValueError:
        return 0.6


def closest_cre_rows(prompt: str) -> List[Dict[str, Any]]:
    """The CRE closest to the question (``[]`` when none is close enough or on any failure).

    OpenCRE chat exists to connect a control question to its Common Requirement, so every
    evidence answer carries this row even when the answer text comes from other sources.
    """
    try:
        from application.database import db as db_mod
        from application.utils.comprehension.embedcache import embed_many
        from application.utils.comprehension.shared import shared_handler

        database = db_mod.Node_collection()
        handler = shared_handler(database)
        vec = embed_many([prompt], handler.get_text_embeddings)[0]
        found = handler.get_id_of_most_similar_cre_paginated(
            list(vec), similarity_threshold=_cre_attach_threshold()
        )
        if not found or not found[0]:
            return []
        cre = database.get_cre_by_db_id(found[0])
        return [cre.shallow_copy().todict()] if cre else []
    except Exception:  # noqa: BLE001 - an extra reference must never fail an answer
        logger.info("closest CRE lookup failed", exc_info=True)
        return []


def encode_citation_urls(response: Any) -> Any:
    """Percent-encode spaces in citation URLs (repo file names like "4. Train your people.md").

    A raw space breaks markdown links and makes the reference unclickable. Elementwise, so the
    ``[n]`` marker to citation positions do not change.
    """
    if not isinstance(response, dict):
        return response
    meta = response.get("owasp_agent")
    if not isinstance(meta, dict) or not isinstance(meta.get("citations"), list):
        return response
    cites = [
        c.replace(" ", "%20") if isinstance(c, str) else c for c in meta["citations"]
    ]
    if cites == meta["citations"]:
        return response
    return {**response, "owasp_agent": {**meta, "citations": cites}}


def attach_closest_cre(prompt: str, response: Dict[str, Any]) -> Dict[str, Any]:
    """Add the closest CRE to an evidence answer's references and citations (CRE-first bias)."""
    if not isinstance(response, dict) or not response.get("accurate", True):
        return response
    meta = response.get("owasp_agent")
    if not isinstance(meta, dict) or meta.get("kind") != "evidence":
        return response
    rows = closest_cre_rows(prompt)
    if not rows:
        return response
    out = dict(response)
    table = out.get("table")
    out["table"] = rows + [r for r in (table if isinstance(table, list) else []) if r]
    cre_id = str(rows[0].get("id") or "")
    if cre_id:
        url = f"https://opencre.org/cre/{cre_id}"
        cites = list(meta.get("citations") or [])
        if url not in cites:
            out["owasp_agent"] = {**meta, "citations": cites + [url]}
    return out


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
        response = OwaspAgentRouter().handle(prompt or "", history=history or None)
        if not response:
            return response
        return encode_citation_urls(attach_closest_cre(prompt or "", response))
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
