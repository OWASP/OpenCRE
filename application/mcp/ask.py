"""MCP-local ``ask`` tool: structured facts only (no OpenCRE narrative LLM).

Cursor (or another host) synthesizes answers. This tool routes to OWASP
metadata facts and/or CRE retrieval facts based on ``corpus``.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from application.mcp.rest_client import (
    RestClient,
    RestClientError,
    RestRequestError,
    RestResponseError,
)
from application.utils.gap_analysis import OPENCRE_STANDARD_NAME
from application.utils.owasp_agent import is_owasp_agent_enabled
from application.utils.owasp_agent.router import OwaspAgentRouter, classify_intent

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
        },
        "required": ["prompt"],
        "additionalProperties": False,
    },
}


def ask(
    prompt: str,
    *,
    corpus: str = CORPUS_AUTO,
    place: Optional[str] = None,
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

    intent = classify_intent(effective)

    if corpus_key == CORPUS_SECURITY:
        return _security_facts(text, rest_client=rest_client, intent=intent)

    if corpus_key == CORPUS_OWASP_META:
        return _owasp_meta_facts(effective, intent=intent, allow_cre_defer=False)

    # auto: meta answer wins when the router handled it; otherwise CRE facts.
    meta = _owasp_meta_facts(effective, intent=intent, allow_cre_defer=True)
    if meta.get("defer_to_security") or meta.get("channel") == "none":
        return _security_facts(text, rest_client=rest_client, intent=intent)
    return meta


def _owasp_meta_facts(
    prompt: str,
    *,
    intent: str,
    allow_cre_defer: bool,
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

    if intent == "cre_normative" and allow_cre_defer:
        return {
            "ok": False,
            "channel": "none",
            "intent": intent,
            "defer_to_security": True,
            "message": "CRE/security question; deferring to CRE fact pack.",
        }

    resp = OwaspAgentRouter().handle(prompt)
    if resp is None:
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
                "No OWASP metadata match. " "Try corpus=security or CRE MCP tools."
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
        "owasp_agent": owasp_meta,
        "citations": list(owasp_meta.get("citations") or []),
        "standards_filter": None,
    }


def _security_facts(
    prompt: str,
    *,
    rest_client: Optional[RestClient],
    intent: str,
) -> Dict[str, Any]:
    client = rest_client or RestClient()
    try:
        search_data = client.call_tool("text_search", {"text": prompt}).data
    except RestResponseError as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "channel": CORPUS_SECURITY,
                "intent": intent,
                "items": [],
                "message": "No CRE/standard matches the search terms.",
                "citations": [],
                "standards_filter": "all_mapped",
            }
        raise
    except RestClientError:
        raise

    docs = _as_doc_list(search_data)
    cre_docs = [d for d in docs if _is_cre_doc(d)]
    if not cre_docs:
        # Only accept CRE-shaped ids (e.g. 622-203), never Standard composite keys.
        cre_docs = [
            d
            for d in docs
            if isinstance(d.get("id"), str) and _looks_like_cre_id(str(d["id"]))
        ]

    selection, standards_filter = _myopencre_selection(client)
    items: List[Dict[str, Any]] = []
    citations: List[str] = []

    for doc in cre_docs[:_MAX_CRE_ENRICH]:
        cre_id = str(doc.get("id") or "").strip()
        if not cre_id:
            continue
        enriched = doc
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

        items.append(
            {
                "cre_id": cre_id,
                "name": enriched.get("name") or doc.get("name"),
                "description": enriched.get("description") or doc.get("description"),
                "url": cre_url,
                "standards": standards,
            }
        )

    return {
        "ok": bool(items),
        "channel": CORPUS_SECURITY,
        "intent": intent,
        "items": items,
        "message": (
            f"Found {len(items)} CRE fact item(s)."
            if items
            else "No CRE documents matched."
        ),
        "citations": _dedupe_preserve(citations),
        "standards_filter": standards_filter,
    }


def _as_doc_list(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("data", "results", "documents"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [d for d in nested if isinstance(d, dict)]
        return [data]
    return []


def _is_cre_doc(doc: Mapping[str, Any]) -> bool:
    doctype = str(doc.get("doctype") or "").lower()
    return doctype == "cre"


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
        out.append(
            {
                "name": name.strip(),
                "section": doc.get("section"),
                "subsection": doc.get("subsection"),
                "hyperlink": doc.get("hyperlink"),
            }
        )
    return out


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
