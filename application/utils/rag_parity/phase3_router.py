"""Phase 3: LangChain tool-calling router (strangler behind flags).

When ``CRE_RAG_PARITY_LC_ROUTER=0``, callers keep the hand-rolled regex path.
This module never auto-links — it only routes intents to tool names.
Production LC path uses real LangChain tool schemas via ``owasp_agent.lc_router``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence

from application.utils.rag_parity.flags import RagParityFlags, load_flags

ROUTER_TOOLS: Dict[str, Dict[str, object]] = {
    "retrieve_cre": {
        "description": "Retrieve CRE candidates for a control/requirement text",
        "parameters": {"query": "string", "top_k": "integer"},
    },
    "map_standard_section": {
        "description": "Map a standard section id to CRE candidates",
        "parameters": {"standard": "string", "section_id": "string"},
    },
    "ask_human": {
        "description": "Escalate low-confidence or ambiguous requests to a human",
        "parameters": {"reason": "string"},
    },
}


@dataclass(frozen=True)
class RouteDecision:
    tool: str
    args: Dict[str, object]
    backend: str  # regex | langchain | langchain_fallback_regex


_SECTION_RE = re.compile(
    r"\b([A-Za-z][\w .-]{1,40})\s+(?:section|control)\s+([A-Za-z0-9][\w./-]{0,40})",
    re.I,
)


def regex_route(text: str) -> RouteDecision:
    """Hand-rolled fallback (to be bypassed when LC flag is on)."""
    blob = (text or "").strip()
    m = _SECTION_RE.search(blob)
    if m:
        return RouteDecision(
            tool="map_standard_section",
            args={"standard": m.group(1).strip(), "section_id": m.group(2).strip()},
            backend="regex",
        )
    if not blob:
        return RouteDecision(
            tool="ask_human", args={"reason": "empty_input"}, backend="regex"
        )
    return RouteDecision(
        tool="retrieve_cre", args={"query": blob, "top_k": 20}, backend="regex"
    )


def langchain_route(
    text: str,
    *,
    llm_router: Optional[Callable[[str, Sequence[str]], str]] = None,
) -> RouteDecision:
    """Real LangChain tool-calling when available; injected llm_router for tests."""
    tools = list(ROUTER_TOOLS.keys())
    if llm_router is not None:
        choice = (llm_router(text, tools) or "").strip()
        if choice not in ROUTER_TOOLS:
            return RouteDecision(
                tool="ask_human",
                args={"reason": f"unknown_tool:{choice}"},
                backend="langchain",
            )
        if choice == "map_standard_section":
            base = regex_route(text)
            if base.tool == "map_standard_section":
                return RouteDecision(tool=choice, args=base.args, backend="langchain")
            return RouteDecision(
                tool="ask_human",
                args={"reason": "map_without_section"},
                backend="langchain",
            )
        if choice == "ask_human":
            return RouteDecision(
                tool=choice, args={"reason": "llm_escalation"}, backend="langchain"
            )
        return RouteDecision(
            tool="retrieve_cre",
            args={"query": (text or "").strip(), "top_k": 20},
            backend="langchain",
        )

    try:
        from application.utils.owasp_agent.lc_router import classify_intent_langchain

        intent = classify_intent_langchain(text)
        if intent:
            tool = "ask_human" if intent in ("clarify", "ask_human") else "retrieve_cre"
            args: Dict[str, object] = (
                {"reason": "lc_escalation"}
                if tool == "ask_human"
                else {"query": (text or "").strip(), "top_k": 20}
            )
            return RouteDecision(tool=tool, args=args, backend="langchain")
    except Exception:  # noqa: BLE001
        pass
    base = regex_route(text)
    return RouteDecision(
        tool=base.tool, args=base.args, backend="langchain_fallback_regex"
    )


def route(
    text: str,
    flags: Optional[RagParityFlags] = None,
    *,
    llm_router: Optional[Callable[[str, Sequence[str]], str]] = None,
) -> RouteDecision:
    cfg = flags or load_flags()
    if cfg.lc_router:
        return langchain_route(text, llm_router=llm_router)
    return regex_route(text)
