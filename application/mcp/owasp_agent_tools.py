"""MCP-local OWASP metadata tools (not CRE graph / not public REST).

These tools read only the experimental owasp_agent SQLite index. They must never
write Credoctypes, Node, CRE, or standard embeddings, and they must not appear
in CRE tag/search/graph UI surfaces.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from application.utils.owasp_agent import is_owasp_agent_enabled
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.queries import MetaQueries
from application.utils.owasp_agent.router import OwaspAgentRouter

# Local MCP tools — not bound to OpenAPI /rest/v1 CRE endpoints.
OWASP_META_TOOLS: Tuple[Dict[str, Any], ...] = (
    {
        "name": "owasp_meta_ask",
        "summary": (
            "Ask an OWASP community/metadata question (chapters, projects, events, "
            "board history). Fail-closed; does not search CREs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Natural-language OWASP metadata question",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_events_near",
        "summary": "Find nearest OWASP events/chapters by place (geocode). Not CRE.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "topic": {"type": "string"},
                "include_past": {"type": "boolean", "default": False},
            },
            "required": ["place"],
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_count_projects",
        "summary": "Count indexed OWASP projects, optionally by topic/level. Not CRE.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "level": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_board",
        "summary": "Look up OWASP board members or candidate history from GitHub YAML.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "name": {"type": "string"},
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_sources_search",
        "summary": (
            "Search the indexed OWASP source text (not CRE). Returns snippets with paths and "
            "citation URLs so a caller can verify an answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {
                    "type": "string",
                    "description": "Optional project, e.g. ASVS",
                },
                "k": {"type": "integer", "default": 8},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_sources_list",
        "summary": "List the indexed source documents of one OWASP project.",
        "input_schema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "required": ["project"],
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_sources_get",
        "summary": "Read one indexed source document of a project in full (truncated at max_chars).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 20000},
            },
            "required": ["project", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "owasp_meta_sources_overview",
        "summary": "Short generated overview of an OWASP project (structure, editions, scope).",
        "input_schema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "required": ["project"],
            "additionalProperties": False,
        },
    },
)

_OWASP_META_BY_NAME = {t["name"]: t for t in OWASP_META_TOOLS}


def list_owasp_meta_tool_names() -> List[str]:
    if not is_owasp_agent_enabled():
        return []
    return [t["name"] for t in OWASP_META_TOOLS]


def get_owasp_meta_tool(name: str) -> Optional[Dict[str, Any]]:
    if not is_owasp_agent_enabled():
        return None
    return _OWASP_META_BY_NAME.get(name)


def call_owasp_meta_tool(
    name: str, arguments: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Dispatch a local meta tool. Raises KeyError if unknown or disabled."""
    if not is_owasp_agent_enabled():
        raise KeyError("OWASP metadata tools are disabled (OWASP_AGENT_ENABLED)")
    if name not in _OWASP_META_BY_NAME:
        raise KeyError(f"Unknown OWASP meta tool: {name}")
    args = dict(arguments or {})
    if name.startswith("owasp_meta_sources_"):
        return _call_sources_tool(name, args)
    store = IndexStore()
    queries = MetaQueries(store)

    if name == "owasp_meta_ask":
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        resp = OwaspAgentRouter(store=store, queries=queries).handle(prompt)
        if resp is None:
            return {
                "ok": False,
                "channel": "owasp_meta",
                "message": (
                    "That looks like a CRE/security question. "
                    "Use CRE MCP tools (get_cre_by_id, text_search, …) instead."
                ),
            }
        owasp_meta = resp.get("owasp_agent") or {}
        # Prefer nested ok; fall back to top-level accurate from format_chat_response.
        if "ok" in owasp_meta:
            ok = bool(owasp_meta.get("ok"))
        else:
            ok = bool(resp.get("accurate"))
        return {
            "ok": ok,
            "channel": "owasp_meta",
            "response": resp.get("response"),
            "owasp_agent": owasp_meta,
            "citations": owasp_meta.get("citations") or [],
        }

    if name == "owasp_meta_events_near":
        result = queries.events_near(
            place=args.get("place"),
            topic=args.get("topic"),
            include_past=bool(args.get("include_past")),
            upcoming_only=not bool(args.get("include_past")),
        )
        return _result_payload(result)

    if name == "owasp_meta_count_projects":
        result = queries.count_projects(
            topic=args.get("topic"), level=args.get("level")
        )
        return _result_payload(result)

    if name == "owasp_meta_board":
        names = args.get("names") or []
        if names:
            result = queries.board_candidate_stats(list(names))
            return _result_payload(result)
        if args.get("name"):
            result = queries.board_person(
                str(args["name"]),
                year=int(args["year"]) if args.get("year") is not None else None,
            )
            return _result_payload(result)
        if args.get("year") is not None:
            result = queries.board_members(int(args["year"]))
            return _result_payload(result)
        raise ValueError("Provide year, name, and/or names")

    raise KeyError(f"Unknown OWASP meta tool: {name}")


def _result_payload(result: Any) -> Dict[str, Any]:
    return {
        "ok": bool(result.ok),
        "channel": "owasp_meta",
        "kind": result.kind,
        "message": result.message,
        "clarify": result.clarify,
        "data": result.data,
        "citations": list(result.citations or []),
    }


def _call_sources_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    from application import sqla
    from application.utils.comprehension import toolkit

    with sqla.session.get_bind().connect() as conn:
        if name == "owasp_meta_sources_search":
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("query is required")
            return toolkit.search_sources(
                conn, query, args.get("project"), int(args.get("k") or 8)
            )
        project = str(args.get("project") or "").strip()
        if not project:
            raise ValueError("project is required")
        if name == "owasp_meta_sources_list":
            return toolkit.list_project_docs(conn, project)
        if name == "owasp_meta_sources_overview":
            return toolkit.project_overview(conn, project)
        if name == "owasp_meta_sources_get":
            path = str(args.get("path") or "").strip()
            if not path:
                raise ValueError("path is required")
            return toolkit.get_source(
                conn, project, path, int(args.get("max_chars") or 20000)
            )
    raise KeyError(f"Unknown OWASP meta tool: {name}")
