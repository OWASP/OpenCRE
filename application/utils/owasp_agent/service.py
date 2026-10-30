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


_NAME_MATCH_BONUS = 0.03
_STOP = frozenset(
    "how do does did can could should would what which who why when where is are was the "
    "a an and or of to for in on with my our your i we it this that about from by be as at "
    "prevent avoid stop protect against secure securely best way ways make using use".split()
)


def _significant_words(text: str) -> set:
    """Lower-case content words (3+ letters) of a question or CRE name."""
    import re

    return {
        w
        for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) >= 3 and w not in _STOP
    }


def closest_cre_rows(
    prompt: str, limit: int = 2, margin: float = 0.03
) -> List[Dict[str, Any]]:
    """The CREs closest to the question: the best match plus any within ``margin`` of it.

    OpenCRE chat exists to connect a control question to its Common Requirement(s), so every
    evidence answer carries them even when the answer text comes from other sources. Near-ties
    (e.g. "Escape output against XSS" vs "XSS protection") are all shown instead of picking one.
    ``[]`` when none is close enough or on any failure.
    """
    try:
        from sqlalchemy import text as sql_text

        from application import sqla
        from application.database import db as db_mod
        from application.database.pgvector_utils import to_pgvector_literal
        from application.utils.comprehension.embedcache import embed_many
        from application.utils.comprehension.shared import shared_handler
        from application.utils.owasp_agent.lane_similarity import cosine_exprs

        database = db_mod.Node_collection()
        handler = shared_handler(database)
        vec = embed_many([prompt], handler.get_text_embeddings)[0]
        dist, score = cosine_exprs()
        with sqla.session.get_bind().connect() as conn:
            found = conn.execute(
                sql_text(
                    f"SELECT cre_id, {score} AS s FROM embeddings "
                    "WHERE doc_type = 'CRE' AND embedding_vec IS NOT NULL "
                    f"ORDER BY {dist} LIMIT :n"
                ),
                {"q": to_pgvector_literal(list(vec)), "n": limit * 3},
            ).fetchall()
        if not found or float(found[0].s) < _cre_attach_threshold():
            return []
        words = _significant_words(prompt)
        scored = []
        seen = set()
        for r in found:
            if r.cre_id in seen:
                continue
            seen.add(r.cre_id)
            cre = database.get_cre_by_db_id(r.cre_id)
            if not cre:
                continue
            bonus = _NAME_MATCH_BONUS if words & _significant_words(cre.name) else 0.0
            scored.append((float(r.s) + bonus, cre))
        scored.sort(key=lambda t: -t[0])
        best = scored[0][0] if scored else 0.0
        rows = [
            cre.shallow_copy().todict() for sc, cre in scored if sc >= best - margin
        ][:limit]
        return rows
    except Exception:  # noqa: BLE001 - an extra reference must never fail an answer
        logger.info("closest CRE lookup failed", exc_info=True)
        return []


def attach_closest_cre(prompt: str, response: Dict[str, Any]) -> Dict[str, Any]:
    """Add the closest CRE(s) to an evidence answer's references and citations (CRE-first bias)."""
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
    cites = list(meta.get("citations") or [])
    for row in rows:
        cre_id = str(row.get("id") or "")
        url = f"https://opencre.org/cre/{cre_id}" if cre_id else ""
        if url and url not in cites:
            cites.append(url)
    out["owasp_agent"] = {**meta, "citations": cites}
    return out


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
