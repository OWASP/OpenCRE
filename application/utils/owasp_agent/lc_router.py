"""Real LangChain tool-calling intent router (optional; falls back to regex).

Uses ``langchain_core.tools`` + OpenAI-style tool schemas via LiteLLM — not a
regex path labeled ``backend=langchain``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_LC_WARNED = False

# Map tool names → existing classify_intent / handle() intent strings.
_TOOL_TO_INTENT = {
    "cre_normative": "cre_normative",
    "project_lookup": "project_lookup",
    "person_lookup": "person_lookup",
    "events_near": "events_near",
    "count_projects": "count_projects",
    "count_chapters": "count_chapters",
    "board_members": "board_members",
    "ask_human": "clarify",
    "refuse_malicious": "refuse_malicious",
}


def lc_available() -> bool:
    try:
        from langchain_core.tools import tool  # noqa: F401
        from langchain_core.utils.function_calling import (  # noqa: F401
            convert_to_openai_tool,
        )

        return True
    except Exception:  # noqa: BLE001
        return False


def _warn_once(msg: str) -> None:
    global _LC_WARNED
    if not _LC_WARNED:
        logger.warning(msg)
        _LC_WARNED = True


def _build_tools() -> List[Any]:
    from langchain_core.tools import tool

    @tool
    def cre_normative(query: str) -> str:
        """Map or explain a security control/requirement against OpenCRE (normative)."""
        return query

    @tool
    def project_lookup(project_name: str) -> str:
        """Look up an OWASP project (leaders, description, repo)."""
        return project_name

    @tool
    def person_lookup(person_name: str) -> str:
        """Look up an OWASP community person (leaders, board)."""
        return person_name

    @tool
    def events_near(place: str) -> str:
        """Find OWASP chapter events near a place."""
        return place

    @tool
    def count_projects() -> str:
        """Answer how many OWASP projects exist."""
        return "count_projects"

    @tool
    def count_chapters() -> str:
        """Answer how many OWASP chapters exist."""
        return "count_chapters"

    @tool
    def board_members(year: str = "") -> str:
        """List OWASP foundation board members (optional year)."""
        return year or "board"

    @tool
    def ask_human(reason: str) -> str:
        """Clarify with the user when the question is ambiguous."""
        return reason

    @tool
    def refuse_malicious(reason: str) -> str:
        """Refuse clearly malicious or disallowed requests."""
        return reason

    return [
        cre_normative,
        project_lookup,
        person_lookup,
        events_near,
        count_projects,
        count_chapters,
        board_members,
        ask_human,
        refuse_malicious,
    ]


def classify_intent_langchain(
    text: str,
    *,
    completion_fn: Optional[Callable[..., Any]] = None,
) -> Optional[str]:
    """Return an intent string via LC tool-calling, or None to fall back."""
    if not (text or "").strip():
        return None
    if not lc_available():
        _warn_once(
            "LangChain unavailable for OWASP_CX_LC_ROUTER; falling back to regex router"
        )
        return None
    try:
        from langchain_core.utils.function_calling import convert_to_openai_tool
        from application.prompt_client import litellm_router
    except Exception:  # noqa: BLE001
        _warn_once("LiteLLM/LangChain tool path unavailable; falling back to regex")
        return None

    tools = _build_tools()
    openai_tools = [convert_to_openai_tool(t) for t in tools]
    model = os.environ.get(
        "OWASP_CX_LC_ROUTER_MODEL",
        os.environ.get("OWASP_CX_HELPER_MODEL", "gemini/gemini-2.5-flash-lite"),
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You route OWASP community / OpenCRE questions. "
                "Call exactly one tool that best matches the user intent. "
                "Prefer cre_normative for how-to, mitigations, standards "
                "(ASVS/MASVS/SAMM/Top Ten/WSTG), controls, and mapping. "
                "Prefer project_lookup when an OWASP project/repo is named. "
                "Use person_lookup only for who-is about a named person. "
                "Use events_near only when a place is present. "
                "Use ask_human only when a chapter/meetup/leader ask has no place "
                "and no project/standard content. Never route security how-to "
                "or false-premise security questions to ask_human/events_near."
            ),
        },
        {"role": "user", "content": text},
    ]
    try:
        fn = completion_fn or litellm_router.completion
        resp = fn(
            model=model,
            messages=messages,
            tools=openai_tools,
            tool_choice="required",
            temperature=0.0,
        )
    except Exception:  # noqa: BLE001
        logger.debug("LC tool-calling completion failed", exc_info=True)
        return None

    name = _tool_name_from_response(resp)
    if not name:
        return None
    return _TOOL_TO_INTENT.get(name)


def _tool_name_from_response(resp: Any) -> Optional[str]:
    """Extract first tool call name from LiteLLM / OpenAI-shaped response."""
    try:
        choices = getattr(resp, "choices", None) or resp.get("choices")  # type: ignore[union-attr]
        msg = (
            choices[0].message
            if hasattr(choices[0], "message")
            else choices[0]["message"]
        )
        tool_calls = getattr(msg, "tool_calls", None) or msg.get("tool_calls") or []
        if not tool_calls:
            # Some models return function_call
            fc = getattr(msg, "function_call", None) or msg.get("function_call")
            if fc:
                return getattr(fc, "name", None) or fc.get("name")
            return None
        first = tool_calls[0]
        fn = getattr(first, "function", None) or first.get("function") or first
        return getattr(fn, "name", None) or fn.get("name")
    except Exception:  # noqa: BLE001
        return None


def patch_phase3_router_for_real_lc() -> None:
    """Make ``rag_parity.phase3_router.langchain_route`` use real LC when available."""
    from application.utils.rag_parity import phase3_router as p3

    def _real(text: str, *, llm_router: Optional[Callable] = None):
        intent = classify_intent_langchain(text)
        if intent is None:
            base = p3.regex_route(text)
            return p3.RouteDecision(
                tool=base.tool, args=base.args, backend="langchain_fallback_regex"
            )
        tool = {
            "cre_normative": "retrieve_cre",
            "clarify": "ask_human",
            "ask_human": "ask_human",
        }.get(intent, "retrieve_cre")
        args: Dict[str, object] = (
            {"reason": "lc_escalation"}
            if tool == "ask_human"
            else {"query": (text or "").strip(), "top_k": 20}
        )
        return p3.RouteDecision(tool=tool, args=args, backend="langchain")

    p3.langchain_route = _real  # type: ignore[assignment]
