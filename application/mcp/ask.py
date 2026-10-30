"""MCP-local ``ask`` tool: structured facts only (no OpenCRE narrative LLM).

Cursor (or another host) synthesizes answers. This tool routes to OWASP
metadata facts and/or CRE retrieval facts based on ``corpus``.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import time
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from application.mcp.rest_client import (
    RestClient,
    RestClientError,
)
from application.utils.gap_analysis import OPENCRE_STANDARD_NAME
from application.utils.owasp_agent import is_owasp_agent_enabled
from application.utils.owasp_agent.router import (
    NOT_SURE_FALLBACK,
    OwaspAgentRouter,
    classify_intent,
)

CORPUS_AUTO = "auto"
CORPUS_SECURITY = "security"
CORPUS_OWASP_META = "owasp_meta"
VALID_CORPORA = frozenset({CORPUS_AUTO, CORPUS_SECURITY, CORPUS_OWASP_META})

# Cap enrichment so ask stays cheap for multi-call Cursor workflows.
_MAX_CRE_ENRICH = 5

ASK_TOOL: Dict[str, Any] = {
    "name": "ask",
    "summary": (
        "Return structured OpenCRE facts for a question (no narrative essay). "
        "corpus=auto routes OWASP community/meta vs CRE/security; "
        "corpus=security forces CRE retrieval; corpus=owasp_meta forces metadata. "
        "Use follow-up tools (get_cre_by_id, owasp_meta_events_near, …) for depth."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Natural-language question",
            },
            "corpus": {
                "type": "string",
                "enum": sorted(VALID_CORPORA),
                "default": CORPUS_AUTO,
                "description": (
                    "auto (default): OWASP router then CRE facts; "
                    "security: CRE/standards only; "
                    "owasp_meta: community/metadata only"
                ),
            },
            "place": {
                "type": "string",
                "description": "Optional place hint for geo-sensitive meta questions",
            },
            "history": {
                "type": "array",
                "description": (
                    "Optional earlier turns [{role: user|assistant, content}] so follow-up "
                    "questions keep their context (the web chat sends the same)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["user", "assistant"]},
                        "content": {"type": "string"},
                    },
                    "required": ["role", "content"],
                },
            },
        },
        "required": ["prompt"],
        "additionalProperties": False,
    },
}


RATE_TOOL: Dict[str, Any] = {
    "name": "rate_answer",
    "summary": (
        "Give a thumbs up or down to an earlier ask answer, using its answer_id. "
        "Optional comment says what was wrong or good. Ratings are used to improve answers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer_id": {"type": "string", "description": "answer_id returned by ask"},
            "rating": {"type": "string", "enum": ["up", "down"]},
            "comment": {"type": "string", "description": "Optional short reason"},
        },
        "required": ["answer_id", "rating"],
        "additionalProperties": False,
    },
}

_APP = None


def _ensure_app():
    """Flask app for pgvector similarity / IndexStore (MCP stdio has no request ctx)."""
    global _APP
    if _APP is not None:
        return _APP
    from application import create_app

    _APP = create_app(mode="production")
    return _APP


def _router_handle(
    prompt: str, history: Optional[List[Dict[str, str]]] = None
) -> Optional[Dict[str, Any]]:
    """Run the shared OWASP agent entry point inside an app context.

    MCP stdio has no request context; the sim gate needs one for pgvector. Raises
    ``OwaspAgentUnavailable`` (same rule as the web chat) when the agent crashes on a meta question.
    """
    from application.utils.owasp_agent.service import route_question

    try:
        from flask import has_app_context

        if has_app_context():
            return route_question(prompt, history)
    except ImportError:
        pass
    app = _ensure_app()
    with app.app_context():
        return route_question(prompt, history)


def _in_app_context(fn: Any) -> Any:
    """Run ``fn`` inside a Flask app context (MCP has none); None if the app cannot start."""
    from flask import has_app_context

    if has_app_context():
        return fn()
    app = _ensure_app()
    with app.app_context():
        return fn()


def ask(
    prompt: str,
    *,
    corpus: str = CORPUS_AUTO,
    place: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    rest_client: Optional[RestClient] = None,
) -> Dict[str, Any]:
    """Route ``prompt`` and return a fact pack; the pack carries an ``answer_id`` for rating."""
    started = time.monotonic()
    result = _ask_impl(
        prompt, corpus=corpus, place=place, history=history, rest_client=rest_client
    )
    try:
        from application.utils.answer_feedback import attach_answer_id

        elapsed = int((time.monotonic() - started) * 1000)
        return _in_app_context(
            lambda: attach_answer_id(
                result, question=prompt, source="mcp", latency_ms=elapsed
            )
        )
    except Exception:  # noqa: BLE001 -- rating support must never break answering
        return result


def rate_answer(
    answer_id: str, rating: str, comment: Optional[str] = None
) -> Dict[str, Any]:
    """Record a thumbs up/down for an earlier answer."""
    from application.utils.answer_feedback import record_rating

    return _in_app_context(lambda: record_rating(answer_id, rating, comment))


def _ask_impl(
    prompt: str,
    *,
    corpus: str = CORPUS_AUTO,
    place: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    rest_client: Optional[RestClient] = None,
) -> Dict[str, Any]:
    """Route ``prompt`` and return a fact pack for the chosen corpus."""
    text = (prompt or "").strip()
    if not text:
        raise ValueError("prompt is required")

    corpus_key = (corpus or CORPUS_AUTO).strip().lower()
    if corpus_key not in VALID_CORPORA:
        raise ValueError(f"corpus must be one of: {', '.join(sorted(VALID_CORPORA))}")

    place_text = (place or "").strip() or None
    effective = text
    if place_text and corpus_key in (CORPUS_AUTO, CORPUS_OWASP_META):
        effective = f"{text} near {place_text}"

    from application.utils.chat_history import normalize_chat_messages

    history = normalize_chat_messages(history) or None
    intent = classify_intent(effective)

    if corpus_key == CORPUS_SECURITY:
        return _security_facts(text, rest_client=rest_client, intent=intent)

    if corpus_key == CORPUS_OWASP_META:
        return _owasp_meta_facts(
            effective, intent=intent, allow_cre_defer=False, history=history
        )

    # auto: meta answer wins when the router handled it; otherwise CRE facts.
    meta = _owasp_meta_facts(
        effective, intent=intent, allow_cre_defer=True, history=history
    )
    if meta.get("defer_to_security") or meta.get("channel") == "none":
        return _security_facts(text, rest_client=rest_client, intent=intent)
    return meta


def _owasp_meta_facts(
    prompt: str,
    *,
    intent: str,
    allow_cre_defer: bool,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    if not is_owasp_agent_enabled():
        if allow_cre_defer:
            return {
                "ok": False,
                "channel": "none",
                "intent": intent,
                "defer_to_security": True,
                "message": "OWASP metadata agent is disabled; using CRE facts.",
            }
        return {
            "ok": False,
            "channel": "none",
            "intent": intent,
            "message": (
                "OWASP metadata tools are disabled (OWASP_AGENT_ENABLED). "
                "Use corpus=security or CRE tools."
            ),
        }

    # Always try the meta/sim router first — evidence and community cards can
    # answer prompts that classify_intent labels as cre_normative.
    from application.utils.owasp_agent.service import OwaspAgentUnavailable

    try:
        resp = _router_handle(prompt, history)
    except OwaspAgentUnavailable:
        # Same rule as the web chat: never answer a community/meta question from CRE retrieval.
        return {
            "ok": False,
            "channel": CORPUS_OWASP_META,
            "intent": intent,
            "message": "The OWASP agent hit a temporary problem. Please try again.",
        }
    if resp is None:
        if intent == "cre_normative" and not allow_cre_defer:
            return {
                "ok": False,
                "channel": CORPUS_OWASP_META,
                "intent": intent,
                "message": (
                    "That looks like a CRE/security question. "
                    "Call ask with corpus=security or use get_cre_by_id / text_search."
                ),
            }
        if allow_cre_defer:
            return {
                "ok": False,
                "channel": "none",
                "intent": intent,
                "defer_to_security": True,
                "message": "No OWASP metadata match; deferring to CRE fact pack.",
            }
        return {
            "ok": False,
            "channel": CORPUS_OWASP_META,
            "intent": intent,
            "message": (
                "No OWASP metadata match. "
                + NOT_SURE_FALLBACK
                + " For security questions use corpus=security or CRE MCP tools."
            ),
        }

    owasp_meta = resp.get("owasp_agent") or {}
    if "ok" in owasp_meta:
        ok = bool(owasp_meta.get("ok"))
    else:
        ok = bool(resp.get("accurate"))
    return {
        "ok": ok,
        "channel": CORPUS_OWASP_META,
        "intent": intent,
        "message": resp.get("response"),
        "items": owasp_meta.get("data"),
        # The source passages the answer used, so a calling agent can check it.
        "evidence": (owasp_meta.get("data") or {}).get("evidence") or [],
        "owasp_agent": owasp_meta,
        "citations": list(owasp_meta.get("citations") or []),
        "standards_filter": None,
    }


class EmbeddingRetrievalError(RuntimeError):
    """The embedding lookup itself failed (provider, database, app setup).

    Kept distinct from "nothing matched": a crash must not read as an empty result.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def _retrieve_nearest_standard(prompt: str) -> Any:
    """Same embedding retrieval as the chatbot; runs under Flask app context.

    Returns the nearest hit, or ``None`` when nothing is above the threshold.
    Raises ``EmbeddingRetrievalError`` when the lookup itself fails.
    """
    from application.database import db as db_mod
    from application.prompt_client import prompt_client

    def _run() -> Any:
        database = db_mod.Node_collection()
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
        return handler.retrieve_nearest_standard_for_prompt(prompt)

    try:
        return _in_app_context(_run)
    except Exception as exc:
        logger.warning("ask: embedding retrieval failed", exc_info=True)
        raise EmbeddingRetrievalError(type(exc).__name__, str(exc)[:300]) from exc


def _standard_embeddings_exist() -> Optional[bool]:
    """True/False when we can tell whether any Standard embeddings are stored, else None."""
    from application.database import db as db_mod
    from application.defs import cre_defs

    def _check() -> bool:
        database = db_mod.Node_collection()
        found, _pages, _page = database.get_embeddings_by_doc_type_paginated(
            doc_type=cre_defs.Credoctypes.Standard.value, page=1, per_page=1
        )
        return bool(found)

    try:
        return bool(_in_app_context(_check))
    except Exception:
        logger.info("ask: could not check for stored embeddings", exc_info=True)
        return None


def _cre_ids_from_node(node: Any) -> List[str]:
    """Collect CRE external ids linked from a Standard/node."""
    from application.defs import cre_defs

    out: List[str] = []
    seen: Set[str] = set()
    for link in getattr(node, "links", None) or []:
        doc = getattr(link, "document", None)
        if doc is None:
            continue
        doctype = getattr(doc, "doctype", None)
        if doctype != cre_defs.Credoctypes.CRE:
            continue
        cre_id = str(getattr(doc, "id", None) or "").strip()
        if not cre_id or not _looks_like_cre_id(cre_id) or cre_id in seen:
            continue
        seen.add(cre_id)
        out.append(cre_id)
    return out


def _matched_standard_payload(hit: Any) -> Dict[str, Any]:
    node = hit.node
    section = getattr(node, "section", None)
    section_id = getattr(node, "sectionID", None) or getattr(node, "section_id", None)
    hyperlink = getattr(node, "hyperlink", None)
    content = hit.embeddings_content or ""
    return {
        "node_id": hit.node_id,
        "name": getattr(node, "name", None),
        "section": section,
        "sectionID": section_id,
        "description": getattr(node, "description", None),
        "hyperlink": hyperlink,
        "embeddings_content": content[:8000],
        "embeddings_url": hit.embeddings_url or "",
        "similarity": hit.similarity,
    }


def _security_facts(
    prompt: str,
    *,
    rest_client: Optional[RestClient],
    intent: str,
) -> Dict[str, Any]:
    """Retrieve via chatbot embedding similarity; return fact pack (no narrative LLM)."""
    client = rest_client or RestClient()
    empty: Dict[str, Any] = {
        "ok": False,
        "channel": CORPUS_SECURITY,
        "intent": intent,
        "matched_standard": None,
        "items": [],
        "citations": [],
        "standards_filter": "all_mapped",
    }
    try:
        hit = _retrieve_nearest_standard(prompt)
    except EmbeddingRetrievalError as exc:
        return {
            **empty,
            "reason": "retrieval_error",
            "error": {"type": exc.kind, "detail": exc.detail},
            "message": (
                f"Embedding retrieval failed ({exc.kind}). This is a server-side "
                "error, not an absence of matches."
            ),
        }
    if hit is None:
        if _standard_embeddings_exist() is False:
            return {
                **empty,
                "reason": "no_embeddings",
                "message": (
                    "No Standard embeddings are stored in this deployment's database, "
                    "so security facts cannot be matched (the embedding job has not "
                    "been run for standards)."
                ),
            }
        return {
            **empty,
            "reason": "no_match_above_threshold",
            "message": "No CRE/standard embedding match above similarity threshold.",
        }

    matched = _matched_standard_payload(hit)
    selection, standards_filter = _myopencre_selection(client)
    items: List[Dict[str, Any]] = []
    citations: List[str] = []
    from application.utils.owasp_agent.candidate_picker import is_structure_ask

    structural_prompt = is_structure_ask(prompt)

    emb_url = matched.get("embeddings_url") or ""
    if isinstance(emb_url, str) and emb_url.startswith(("http://", "https://")):
        citations.append(emb_url)
    hyperlink = matched.get("hyperlink")
    if isinstance(hyperlink, str) and hyperlink.startswith(("http://", "https://")):
        citations.append(hyperlink)

    for cre_id in _cre_ids_from_node(hit.node)[:_MAX_CRE_ENRICH]:
        enriched: Dict[str, Any] = {"id": cre_id}
        try:
            full = client.call_tool("get_cre_by_id", {"creid": cre_id}).data
            if isinstance(full, dict) and isinstance(full.get("data"), dict):
                enriched = full["data"]
            elif isinstance(full, dict):
                enriched = full
        except RestClientError:
            logger.info("ask: could not enrich CRE %s", cre_id, exc_info=True)

        standards = _extract_standards(enriched)
        if selection is not None:
            standards = [
                s
                for s in standards
                if s.get("name") in selection or s.get("name") == OPENCRE_STANDARD_NAME
            ]

        cre_url = f"https://opencre.org/cre/{cre_id}"
        citations.append(cre_url)
        for std in standards:
            link = std.get("hyperlink")
            if isinstance(link, str) and link.startswith(("http://", "https://")):
                citations.append(link)

        # Keep curated facts on items only — never prepend into message for
        # unrelated CRE hits. Surface linked-standard structure only for
        # structural question shapes (levels / layers / maturity).
        node_facts = _collect_metadata_facts(
            enriched, standards, include_linked_standards=structural_prompt
        )
        item: Dict[str, Any] = {
            "cre_id": cre_id,
            "name": enriched.get("name"),
            "description": enriched.get("description"),
            "url": cre_url,
            "standards": standards,
        }
        if node_facts:
            item["facts"] = node_facts
            from application.utils.owasp_agent.node_facts import format_facts_message

            _msg, fact_cites = format_facts_message(node_facts)
            for cite in fact_cites:
                citations.append(cite)
        items.append(item)

    message = (
        f"Nearest standard match (similarity={matched['similarity']:.3f}); "
        f"{len(items)} linked CRE fact item(s)."
    )

    return {
        "ok": True,
        "channel": CORPUS_SECURITY,
        "intent": intent,
        "matched_standard": matched,
        "items": items,
        "message": message,
        "citations": _dedupe_preserve(citations),
        "standards_filter": standards_filter,
    }


def _looks_like_cre_id(cre_id: str) -> bool:
    parts = cre_id.strip().split("-")
    return len(parts) == 2 and all(p.isdigit() for p in parts)


def _extract_standards(cre_doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for link in cre_doc.get("links") or []:
        if not isinstance(link, dict):
            continue
        doc = link.get("document")
        if not isinstance(doc, dict):
            continue
        doctype = str(doc.get("doctype") or "").lower()
        if doctype and doctype != "standard":
            continue
        name = doc.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        entry: Dict[str, Any] = {
            "name": name.strip(),
            "section": doc.get("section"),
            "subsection": doc.get("subsection"),
            "hyperlink": doc.get("hyperlink"),
        }
        meta = doc.get("metadata")
        if isinstance(meta, dict) and meta.get("facts"):
            entry["metadata"] = {"facts": meta["facts"]}
        out.append(entry)
    return out


def _collect_metadata_facts(
    cre_doc: Mapping[str, Any],
    standards: List[Dict[str, Any]],
    *,
    include_linked_standards: bool = False,
) -> Dict[str, Any]:
    """Collect metadata.facts from the CRE; optionally merge linked standards.

    Linked-standard structure facts (ASVS levels, etc.) are only merged when
    ``include_linked_standards`` is True so unrelated CRE hits do not inherit
    family structure prose.
    """
    merged: Dict[str, Any] = {}
    cre_meta = cre_doc.get("metadata")
    if isinstance(cre_meta, dict):
        facts = cre_meta.get("facts")
        if isinstance(facts, dict):
            merged.update(facts)
    if include_linked_standards:
        for std in standards:
            meta = std.get("metadata")
            if not isinstance(meta, dict):
                continue
            facts = meta.get("facts")
            if isinstance(facts, dict):
                merged.update(facts)
    return merged


def _myopencre_selection(
    client: RestClient,
) -> Tuple[Optional[Set[str]], str]:
    """Return (selection, filter_label). selection None means no narrowing."""
    from application.mcp.catalog import auth_tools_enabled

    if not auth_tools_enabled():
        return None, "all_mapped"

    from application.mcp import auth

    try:
        auth.current_id_token()
    except auth.AuthError:
        return None, "all_mapped"

    try:
        payload = client.call_tool("get_my_resources", {}).data
    except RestClientError:
        logger.info("ask: get_my_resources failed; using all mapped standards")
        return None, "all_mapped"

    selected: List[Any] = []
    if isinstance(payload, dict):
        raw_selected = payload.get("selected") or []
        if isinstance(raw_selected, list):
            selected = raw_selected
    if not selected:
        # Empty selection means "show everything" in the web UI.
        return None, "all_mapped"
    names = {str(n).strip() for n in selected if isinstance(n, str) and n.strip()}
    if not names:
        return None, "all_mapped"
    return names, "myopencre"


def _dedupe_preserve(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
