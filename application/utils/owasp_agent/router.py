"""Intent router + clarification slots for the OWASP agent chat extension."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import QueryResult
from application.utils.owasp_agent.queries import MetaQueries


def is_owasp_agent_enabled() -> bool:
    return os.environ.get("OWASP_AGENT_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@dataclass
class Slots:
    place: Optional[str] = None
    topic: Optional[str] = None
    year: Optional[int] = None
    person: Optional[str] = None
    persons: List[str] = field(default_factory=list)
    include_past: bool = False
    level: Optional[str] = None


class OwaspAgentRouter:
    """Rule-based router: community/meta vs CRE normative.

    When intent is CRE normative, returns None from handle() so the caller
    falls through to existing PromptHandler.generate_text.
    """

    def __init__(
        self,
        store: Optional[IndexStore] = None,
        queries: Optional[MetaQueries] = None,
        geocode_fn=None,
    ) -> None:
        self.store = store or IndexStore()
        if queries is not None:
            self.queries = queries
        elif geocode_fn is not None:
            self.queries = MetaQueries(self.store, geocode_fn=geocode_fn)
        else:
            self.queries = MetaQueries(self.store)

    def handle(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Return a chat response dict, or None to defer to CRE RAG."""
        if not is_owasp_agent_enabled():
            return None
        text = (prompt or "").strip()
        if not text:
            return None

        intent = classify_intent(text)
        if intent == "cre_normative":
            return None

        slots = extract_slots(text)
        result = self._dispatch(intent, slots, text)
        return format_chat_response(result)

    def _dispatch(self, intent: str, slots: Slots, text: str) -> QueryResult:
        if intent == "count_chapters":
            return self.queries.count_chapters()
        if intent == "count_projects":
            topic = slots.topic
            if topic is None and _mentions_ai(text):
                topic = "ai_security"
            if topic is None and _mentions_appsec(text):
                topic = "appsec"
            return self.queries.count_projects(topic=topic, level=slots.level)
        if intent == "board_members":
            if slots.year is None:
                return QueryResult(
                    ok=False,
                    kind="board_members",
                    message="Which board year should I look up?",
                    clarify="Please provide a year (e.g. 2024).",
                )
            return self.queries.board_members(slots.year)
        if intent == "board_person":
            if not slots.person:
                return QueryResult(
                    ok=False,
                    kind="board_person",
                    message="Which person should I look up on the board or candidate lists?",
                    clarify="Please give the person's full name.",
                )
            return self.queries.board_person(slots.person, year=slots.year)
        if intent == "board_candidate_stats":
            names = slots.persons or ([slots.person] if slots.person else [])
            return self.queries.board_candidate_stats(names)
        if intent == "events_near":
            upcoming_only = not slots.include_past
            return self.queries.events_near(
                place=slots.place,
                topic=slots.topic or ("ai_security" if _mentions_ai(text) else None),
                upcoming_only=upcoming_only,
                include_past=slots.include_past,
            )
        # Generic meta / semantic fallback: interview for missing context
        return QueryResult(
            ok=False,
            kind="clarify",
            message=(
                "I can help with OWASP chapters, projects, events, and board history. "
                "What would you like to know? If this is about a meetup, which city are you in?"
            ),
            clarify="What OWASP metadata question should I answer?",
        )


def classify_intent(text: str) -> str:
    t = text.lower()
    # Security normative signals → defer to CRE
    normative_hints = (
        "how should i",
        "how do i secure",
        "password",
        "encryption",
        "csrf",
        "xss",
        "sqli",
        "sql injection",
        "asvs",
        "threat model",
        "mitigate",
        "vulnerability",
        "cwe-",
    )
    meta_hints = (
        "chapter",
        "meetup",
        "meeting",
        "event",
        "how many",
        "board",
        "candidate",
        "nest",
        "owasp project",
        "projects on",
        "nearest",
        "pasadena",
        "staff",
    )
    has_meta = any(h in t for h in meta_hints)
    has_norm = any(h in t for h in normative_hints)
    if has_meta and not has_norm:
        if "how many" in t and "chapter" in t:
            return "count_chapters"
        if "how many" in t and "project" in t:
            return "count_projects"
        if "candidate" in t and ("how many" in t or "times" in t):
            return "board_candidate_stats"
        if "board" in t and ("member" in t or "position" in t or "who" in t):
            if (
                _extract_quoted_or_capitalized_name(text)
                or "year" in t
                or re.search(r"\b20\d{2}\b", t)
            ):
                # person vs year list
                if _extract_quoted_or_capitalized_name(text):
                    return "board_person"
            if re.search(r"\b20\d{2}\b", t) and "who" in t:
                return "board_members"
            if "position" in t or "board member" in t:
                return "board_person"
            return "board_members"
        if any(
            w in t for w in ("nearest", "meetup", "meeting", "event", "chapter near")
        ):
            return "events_near"
        if "project" in t and ("ai" in t or "appsec" in t):
            return "count_projects"
        return "clarify"
    if has_norm and not has_meta:
        return "cre_normative"
    if has_norm and has_meta:
        # Prefer meta when clearly community; else CRE
        if any(w in t for w in ("meetup", "chapter", "board", "how many")):
            if "how many" in t and "chapter" in t:
                return "count_chapters"
            if "meetup" in t or "nearest" in t:
                return "events_near"
            if "board" in t:
                return "board_person"
        return "cre_normative"
    return "cre_normative"


def extract_slots(text: str) -> Slots:
    slots = Slots()
    t = text.lower()

    m_year = re.search(r"\b(20\d{2})\b", text)
    if m_year:
        slots.year = int(m_year.group(1))

    if any(w in t for w in ("past", "previous", "last year", "history", "historical")):
        slots.include_past = True

    if "flagship" in t:
        slots.level = "flagship"
    elif "incubator" in t:
        slots.level = "incubator"

    if _mentions_ai(t):
        slots.topic = "ai_security"
    elif _mentions_appsec(t):
        slots.topic = "appsec"

    # Place: "in Pasadena", "I'm in X", "near Los Angeles"
    m_place = re.search(
        r"\b(?:in|near|around|from)\s+([A-Z][A-Za-z .'-]+(?:,\s*[A-Z]{2})?)",
        text,
    )
    if m_place:
        slots.place = m_place.group(1).strip().rstrip(".?!")

    # Explicit "I am in ..."
    m_place2 = re.search(
        r"\b(?:i(?:'m| am)|we are)\s+(?:in|near)\s+([A-Za-z .',-]+)",
        text,
        re.IGNORECASE,
    )
    if m_place2:
        slots.place = m_place2.group(1).strip().rstrip(".?!")

    person = _extract_quoted_or_capitalized_name(text)
    if person:
        slots.person = person

    # "X, Y, and Z" candidacy lists
    m_list = re.search(
        r"(?:candidates?|names?|people)\s+([A-Z][^?.!]*)",
        text,
    )
    if m_list:
        raw = m_list.group(1)
        parts = re.split(r",| and ", raw)
        slots.persons = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]

    # "how many times ... X, Y, and Z"
    m_times = re.search(
        r"how many times.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)+(?:\s*,?\s*and\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)?)",
        text,
    )
    if m_times:
        raw = m_times.group(1)
        parts = re.split(r",| and ", raw)
        slots.persons = [p.strip() for p in parts if p.strip()]

    return slots


def format_chat_response(result: QueryResult) -> Dict[str, Any]:
    text = result.message
    if result.clarify and not result.ok:
        text = f"{result.message}"
    table: List[Any] = []
    if result.citations:
        for url in result.citations:
            table.append({"name": "OWASP source", "link": url, "ntype": "OWASPMeta"})
    safe_data = _sanitize_result_data(result.data)
    return {
        "response": f"Answer: {text}",
        "table": table,
        "accurate": bool(result.ok),
        "model_name": "owasp-agent-router",
        "owasp_agent": {
            "kind": result.kind,
            "ok": result.ok,
            "clarify": result.clarify,
            "data": safe_data,
        },
    }


def _sanitize_result_data(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        out: Dict[str, Any] = {}
        for k, v in data.items():
            if k in ("raw", "origin", "_index_source"):
                continue
            out[k] = _sanitize_result_data(v)
        return out
    if isinstance(data, list):
        return [_sanitize_result_data(x) for x in data]
    return data


def _mentions_ai(text: str) -> bool:
    t = text.lower()
    return (
        any(
            k in t
            for k in (
                "ai security",
                "ai-security",
                "machine learning",
                " llm",
                "genai",
                "artificial intelligence",
                " ai ",
                "ai system",
                "projects on ai",
                "about ai",
            )
        )
        or t.strip().startswith("ai ")
        or " on ai" in t
    )


def _mentions_appsec(text: str) -> bool:
    t = text.lower()
    return "appsec" in t or "application security" in t


def _extract_quoted_or_capitalized_name(text: str) -> Optional[str]:
    m = re.search(r"[\"']([A-Z][^\"']+)[\"']", text)
    if m:
        return m.group(1).strip()
    # "position of X" / "board member X"
    m2 = re.search(
        r"(?:position of|board member|member|candidate)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        text,
    )
    if m2:
        return m2.group(1).strip()
    return None
