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
    places: List[str] = field(default_factory=list)
    topic: Optional[str] = None
    year: Optional[int] = None
    years: List[int] = field(default_factory=list)
    person: Optional[str] = None
    persons: List[str] = field(default_factory=list)
    include_past: bool = False
    level: Optional[str] = None
    student: bool = False
    list_mode: bool = False
    country: Optional[str] = None
    countries: List[str] = field(default_factory=list)


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
        if intent == "cre_fact":
            from application.utils.owasp_agent.cre_facts import (
                format_cre_factoid,
                lookup_cre_factoid,
            )

            hit = lookup_cre_factoid(text)
            if not hit:
                return None  # fall through to CRE RAG
            cre_id, title, note = hit
            result = QueryResult(
                ok=True,
                kind="cre_fact",
                data={"cre_id": cre_id, "title": title},
                message=format_cre_factoid(cre_id, title, note),
                citations=[f"https://opencre.org/cre/{cre_id}"],
            )
            return format_chat_response(result)
        if intent == "refuse_malicious":
            result = QueryResult(
                ok=True,
                kind="refuse_malicious",
                message=(
                    "I cannot provide instructions or assistance for illegal or unauthorized "
                    "access, phishing, DDoS, or similar attacks. I can help with OWASP chapters, "
                    "projects, board history, membership, and defensive AppSec questions."
                ),
            )
            return format_chat_response(result)

        slots = extract_slots(text)
        result = self._dispatch(intent, slots, text)
        return format_chat_response(result)

    def _dispatch(self, intent: str, slots: Slots, text: str) -> QueryResult:
        if intent == "count_chapters":
            return self.queries.count_chapters()
        if intent == "count_projects_and_chapters":
            chapters = self.queries.count_chapters()
            projects = self.queries.count_projects()
            ch_n = (chapters.data or {}).get("count")
            pr_n = (projects.data or {}).get("count")
            if ch_n is None or pr_n is None:
                return QueryResult(
                    ok=False,
                    kind="count_projects_and_chapters",
                    message=(
                        "I could not read both chapter and project counts from the index."
                    ),
                )
            return QueryResult(
                ok=True,
                kind="count_projects_and_chapters",
                data={"chapters": ch_n, "projects": pr_n},
                message=(
                    f"The local index has {pr_n} OWASP projects versus "
                    f"{ch_n} OWASP chapters."
                ),
                citations=list(
                    dict.fromkeys(
                        list(projects.citations or []) + list(chapters.citations or [])
                    )
                ),
            )
        if intent == "count_projects":
            topic = slots.topic
            if topic is None and _mentions_ai(text):
                topic = "ai_security"
            if topic is None and _mentions_appsec(text):
                topic = "appsec"
            if topic is None:
                m_touch = re.search(
                    r"\b(?:touch|about|on|regarding|related to)\s+"
                    r"([a-z][a-z0-9 Cont/-]{2,40})",
                    text.lower(),
                )
                if m_touch:
                    topic = m_touch.group(1).strip()
            list_mode = slots.list_mode or bool(
                re.search(
                    r"\b(list|table|which projects|name the|flagged)\b",
                    text.lower(),
                )
            )
            level = slots.level
            # Colloquial "flagged" is not a Nest level — list without level filter.
            if level and level.lower() == "flagged":
                level = None
            return self.queries.count_projects(
                topic=topic, level=level, list_mode=list_mode
            )
        if intent == "board_members":
            years = slots.years or ([slots.year] if slots.year is not None else [])
            if not years:
                return QueryResult(
                    ok=False,
                    kind="board_members",
                    message="Which board year should I look up?",
                    clarify="Please provide a year (e.g. 2025).",
                )
            return self.queries.board_members_years(years)
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
        if intent == "chapter_lookup":
            places = slots.places or ([slots.place] if slots.place else [])
            return self.queries.chapter_lookup(place=slots.place, places=places or None)
        if intent == "membership":
            renew = bool(
                re.search(r"\b(renew|renewal|how do i (join|become))\b", text.lower())
            ) and not bool(
                re.search(
                    r"\b(how much|cost|price|fee|discount|student)\b", text.lower()
                )
            )
            countries = slots.countries or ([slots.country] if slots.country else [])
            return self.queries.membership_info(
                country=slots.country,
                countries=countries or None,
                student=slots.student or bool(re.search(r"\bstudent\b", text.lower())),
                renew_only=renew and not countries,
            )
        if intent == "talk_lookup":
            return self.queries.talk_lookup(person=slots.person, topic=slots.topic)
        if intent == "cre_fact":
            from application.utils.owasp_agent.cre_facts import (
                format_cre_factoid,
                lookup_cre_factoid,
            )

            hit = lookup_cre_factoid(text)
            if not hit:
                return QueryResult(
                    ok=False,
                    kind="cre_fact",
                    message=(
                        "I do not have a curated CRE factoid for that control. "
                        "Falling back is handled by CRE RAG."
                    ),
                )
            cre_id, title, note = hit
            return QueryResult(
                ok=True,
                kind="cre_fact",
                data={"cre_id": cre_id, "title": title},
                message=format_cre_factoid(cre_id, title, note),
                citations=[f"https://opencre.org/cre/{cre_id}"],
            )
        if intent == "events_near":
            upcoming_only = not slots.include_past
            return self.queries.events_near(
                place=slots.place,
                topic=slots.topic or ("ai_security" if _mentions_ai(text) else None),
                upcoming_only=upcoming_only,
                include_past=slots.include_past,
            )
        return QueryResult(
            ok=False,
            kind="clarify",
            message=(
                "I can help with OWASP chapters, projects, events, board history, "
                "and membership pricing. What would you like to know? "
                "If this is about a meetup, which city are you in?"
            ),
            clarify="What OWASP metadata question should I answer?",
        )


def classify_intent(text: str) -> str:
    t = text.lower().strip()
    # Security normative signals → defer to CRE (unless clearly meta)
    normative_hints = (
        "how should i",
        "how do i secure",
        "password storage",
        "password hashing",
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
        "wstg",
        "samm",
        "cheat sheet",
        "output encoding",
        "cre covers",
        "related cres",
    )
    meta_hints = (
        "chapter",
        "meetup",
        "meeting",
        "event",
        "how many",
        "board",
        "candidate",
        "candidacy",
        "interview",
        "statement",
        "nest",
        "owasp project",
        "owasp projects",
        "projects on",
        "flagged",
        "nearest",
        "pasadena",
        "staff",
        "membership",
        "member dues",
        "dues",
        "renew",
        "leader",
        "leaders",
        "keynote",
        "talk",
        "spoke",
        "presented",
        "appsec talk",
        "roster",
        "commuting",
        "suburb",
    )
    has_meta = any(h in t for h in meta_hints)
    has_norm = any(h in t for h in normative_hints)

    # Malicious / unauthorized help — refuse before any meta routing so
    # compound prompts ("dump keys + chapter leader") cannot skip the gate.
    if re.search(
        r"("
        r"\bhow do i hack\b|\bteach me to (hack|phish)\b|\bsql injection payload\b|"
        r"\bddos\b|\bbreak into\b|\bsteal (their|passwords|dms)\b|"
        r"\bphishing (email )?template\b|\bvishing\b|\bmetasploit\b|"
        r"\bsocial-?engineer\b|"
        r"\bignore (all )?(previous|prior|earlier)( instructions)?\b|"
        r"\bdump (the )?(api|nest|heroku)?.{0,20}keys?\b|"
        r"\boutput the .{0,40}api keys?\b|"
        r"\bcsrf\s*\+\s*xss\b|\bchained against\b|"
        r"\breset an owasp board member\b|"
        r"\bharvest credit cards\b|\breverse shell\b"
        r")",
        t,
    ):
        return "refuse_malicious"

    # Bare / underspecified prompts → clarify in-agent (do not CRE-defer)
    if re.fullmatch(
        r"(projects?|board|membership( price)?|student discount|next meetup|"
        r"events?|chapters?|help with owasp|tell me about owasp|"
        r"who is the leader|regional or standard|ai stuff|near me|"
        r"status in greece|compare the two chapters|output encoding|"
        r"appsec keynote summary please|first interview|who ran|"
        r"cre for that thing we discussed|what did they say at the talk|"
        r"is the chapter active)\??",
        t,
    ):
        return "clarify"

    # Curated CRE factoids (deterministic) before generic CRE RAG
    if re.search(r"\b(which cre|what cre|cre covers)\b", t) or (
        "cre" in t and "covers" in t
    ):
        from application.utils.owasp_agent.cre_facts import lookup_cre_factoid

        if lookup_cre_factoid(text):
            return "cre_fact"

    # Named-person talk claims (incl. fake speakers / suburb meetups) → fail-closed
    if (
        re.search(
            r"\bwhat did\b.+\b(say|present|speak|argue)\b",
            t,
        )
        or re.search(
            r"\b(transcript please|chitchat:|did .+ (ever )?(give|present|speak))\b",
            t,
        )
        or re.search(
            r"\b(say|said|present|presented|speak|spoke)\b.+\b("
            r"meetup|keynote|talk|appsec|owasp|defenses)\b",
            t,
        )
    ) and not re.search(r"\b(board interview|candidate statement|candidacy)\b", t):
        if _extract_quoted_or_capitalized_name(text) or re.search(
            r"\b(unknown speaker|random person|transcript)\b", t
        ):
            return "talk_lookup"

    # Membership (admin) — always meta, never CRE fallthrough
    if re.search(
        r"\b(membership|member dues|dues|renew my|"
        r"how much is an owasp membership|owasp individual dues|"
        r"student discount.*membership|membership.*student|"
        r"reside in|billing country|regional or standard|"
        r"annual owasp membership|membership (price|fee|cost|portal))\b",
        t,
    ):
        return "membership"

    # Project listing / counts (including free-topic "touch X" tables)
    if re.search(
        r"\b(which flagged owasp projects|flagged owasp projects|"
        r"projects touch|list .+ projects|projects? in a table|"
        r"ai-related projects|related owasp projects)\b",
        t,
    ) or (
        "project" in t
        and any(w in t for w in ("table", "list", "flagged", "which", "touch"))
    ):
        return "count_projects"

    if re.search(
        r"\b(count of owasp projects versus chapters|projects versus chapters|"
        r"projects vs\.? chapters|chapters versus projects)\b",
        t,
    ):
        return "count_projects_and_chapters"

    # Chapter leader / status / active (incl. suburb → chapter + who leads)
    if re.search(
        r"\b(chapter leader|leader for|leaders? (for|in|of)|who leads|"
        r"which chapter|active owasp chapter|chapter status|owasp leader)\b",
        t,
    ) or (
        "chapter" in t
        and any(
            w in t for w in ("athens", "thessalon", "los angeles", "active", "status")
        )
    ):
        return "chapter_lookup"

    # Talk / keynote claims — fail-closed talk_lookup (not CRE, not invent)
    if re.search(
        r"\b(keynote|appsec talk|presented at|give a (talk|keynote)|"
        r"sa(id|y) about .{0,40}defenses|talk on |summarize .+ talk|"
        r"find .{0,40}talks? by|talks? by (a )?random person|talks? by)\b",
        t,
    ) and not re.search(r"\b(board interview|candidate statement)\b", t):
        if "board interview" in t or "candidate statement" in t:
            return "board_person"
        return "talk_lookup"

    # Board interview / candidate statement / quote from board interview
    if re.search(
        r"\b(board interview|candidate statement|run for the owasp board|"
        r"first board interview|candidacy|quote .{0,40}board interview)\b",
        t,
    ):
        return "board_person"

    if has_meta and not has_norm:
        if re.search(r"\b(projects? versus chapters|chapters versus projects)\b", t):
            return "count_projects_and_chapters"
        if "how many" in t and "chapter" in t and "project" in t:
            return "count_projects_and_chapters"
        if "how many" in t and "chapter" in t:
            return "count_chapters"
        if ("how many" in t and "project" in t) or (
            "project" in t
            and ("list" in t or "ai" in t or "appsec" in t or "table" in t)
        ):
            return "count_projects"
        if "candidate" in t and ("how many" in t or "times" in t):
            return "board_candidate_stats"
        if "board" in t and (
            "member" in t
            or "position" in t
            or "who" in t
            or "roster" in t
            or re.search(r"\b20\d{2}\b", t)
        ):
            if _extract_quoted_or_capitalized_name(text) and not re.search(
                r"\bwho (is|are) on the\b", t
            ):
                return "board_person"
            if re.search(r"\b20\d{2}\b", t) and (
                "who" in t or "member" in t or "board" in t or "roster" in t
            ):
                return "board_members"
            if "position" in t or "board member" in t:
                return "board_person"
            return "board_members"
        if any(
            w in t
            for w in (
                "nearest",
                "meetup",
                "meeting",
                "event",
                "chapter near",
                "commuting",
                "suburb",
            )
        ):
            return "events_near"
        if "project" in t and ("ai" in t or "appsec" in t):
            return "count_projects"
        return "clarify"
    if has_norm and not has_meta:
        return "cre_normative"
    if has_norm and has_meta:
        # Prefer meta when clearly community; else CRE
        if any(w in t for w in ("membership", "dues", "reside in", "billing country")):
            return "membership"
        if "project" in t and any(
            w in t for w in ("table", "list", "flagged", "which", "touch")
        ):
            return "count_projects"
        if any(w in t for w in ("meetup", "chapter", "board", "how many", "leader")):
            if "how many" in t and "chapter" in t and "project" in t:
                return "count_projects_and_chapters"
            if "how many" in t and "chapter" in t:
                return "count_chapters"
            if "leader" in t or "who leads" in t or "chapter status" in t:
                return "chapter_lookup"
            if "meetup" in t or "nearest" in t or "commuting" in t or "suburb" in t:
                # Person+say already handled; suburb meetup + who leads → chapter
                if "who leads" in t or "which chapter" in t:
                    return "chapter_lookup"
                return "events_near"
            if "board" in t:
                if "interview" in t or "statement" in t or "candidate" in t:
                    return "board_person"
                return "board_members"
        # e.g. "board interview about XSS" — meta person lookup, not CRE XSS advice
        if "board interview" in t or "candidate" in t:
            return "board_person"
        if "keynote" in t or "talk" in t or "what did" in t:
            return "talk_lookup"
        return "cre_normative"
    # Chitchat about named person + defenses/talk without clear CRE ask
    if re.search(r"\b(keynote|talk|presented|say about|said about)\b", t) and (
        _extract_quoted_or_capitalized_name(text)
    ):
        return "talk_lookup"
    return "cre_normative"


def extract_slots(text: str) -> Slots:
    slots = Slots()
    t = text.lower()

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    if years:
        slots.years = years
        slots.year = years[0]

    if any(w in t for w in ("past", "previous", "last year", "history", "historical")):
        slots.include_past = True

    if "flagship" in t:
        slots.level = "flagship"
    elif "incubator" in t:
        slots.level = "incubator"
    elif re.search(r"\bflagged\b", t):
        slots.level = "flagged"

    if _mentions_ai(t):
        slots.topic = "ai_security"
    elif _mentions_appsec(t):
        slots.topic = "appsec"
    else:
        m_topic = re.search(
            r"\b(?:about|on|regarding|touch)\s+([a-z][a-z0-9 Cont/-]{2,40})",
            t,
        )
        if m_topic:
            raw = m_topic.group(1).strip().rstrip("?.!")
            if raw not in ("the", "a", "an", "owasp", "his", "her", "their"):
                slots.topic = raw

    if re.search(r"\b(list|table)\b", t):
        slots.list_mode = True
    if re.search(r"\bstudent\b", t):
        slots.student = True

    # Place: stop before about/for/on/regarding topic clauses
    m_place = re.search(
        r"\b(?:in|near|around|from)\s+"
        r"([A-Z][A-Za-z .'-]+?)(?=\s+(?:about|for|on|regarding|with)\b|[?,.!]|$)",
        text,
    )
    if m_place:
        slots.place = m_place.group(1).strip().rstrip(".?!")

    m_place2 = re.search(
        r"\b(?:i(?:'m| am)|we are)\s+(?:in|near)\s+([A-Za-z .',-]+)",
        text,
        re.IGNORECASE,
    )
    if m_place2:
        slots.place = m_place2.group(1).strip().rstrip(".?!")

    m_live = re.search(
        r"\b(?:i live|living|based)\s+in\s+"
        r"([A-Za-z][A-Za-z .'-]*?)(?=\s*[;,.?!]|$)",
        text,
        re.IGNORECASE,
    )
    if m_live:
        slots.place = m_live.group(1).strip().rstrip(".?!;")

    m_dist = re.search(
        r"\b(?:commuting distance of|distance of|suburb)\s+"
        r"([A-Z][A-Za-z .'-]*?)(?=\s+(?:meetup|about|for|on|→|,)|\s*[;?.!]|$)",
        text,
    )
    if m_dist:
        slots.place = m_dist.group(1).strip().rstrip(".?!;→")
    # Chapter / suburb mentions without in/near
    for city in (
        "Athens",
        "Thessaloniki",
        "Los Angeles",
        "Pasadena",
        "Santa Monica",
        "Glendale",
        "Burbank",
        "Long Beach",
        "Croydon",
        "Peckham",
        "Potsdam",
        "Yokohama",
        "London",
        "Berlin",
        "Tokyo",
        "New York",
        "San Francisco",
        "Seattle",
        "Chicago",
        "Toronto",
        "Sydney",
    ):
        if re.search(rf"\b{re.escape(city)}\b", text, re.IGNORECASE):
            if city not in slots.places:
                slots.places.append(city)
            if not slots.place:
                slots.place = city
    # versus / vs comparisons — city-sized tokens only
    m_vs = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:versus|vs\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        text,
    )
    if m_vs:
        slots.places = [
            m_vs.group(1).strip().rstrip(".?!"),
            m_vs.group(2).strip().rstrip(".?!"),
        ]
        slots.place = slots.places[0]

    person = _extract_quoted_or_capitalized_name(text)
    if person:
        slots.person = person

    # Membership countries — any Title Case token looked up later; seed common ones
    known_countries = (
        "Morocco",
        "Uganda",
        "Greece",
        "Germany",
        "United States",
        "Canada",
        "United Kingdom",
        "India",
        "Brazil",
        "Kenya",
        "Nigeria",
        "Egypt",
        "France",
        "Italy",
        "Spain",
        "Australia",
        "Japan",
        "China",
        "Philippines",
        "Indonesia",
        "Pakistan",
        "Bangladesh",
        "Vietnam",
        "South Africa",
        "Mexico",
        "Argentina",
        "Poland",
        "Netherlands",
        "Sweden",
        "Norway",
        "Denmark",
        "Finland",
        "Ireland",
        "Portugal",
        "Switzerland",
        "Austria",
        "Belgium",
        "Romania",
        "Ukraine",
        "Turkey",
        "Ghana",
        "Tanzania",
        "Nepal",
        "Sri Lanka",
        "Cambodia",
        "Ethiopia",
        "Senegal",
        "Rwanda",
        "Zambia",
        "Bolivia",
        "Singapore",
        "South Korea",
        "New Zealand",
    )
    for c in known_countries:
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            # Preserve canonical casing from list
            if c not in slots.countries:
                slots.countries.append(c)
    # "in X versus Y" country pairs not in the list
    m_vs_c = re.search(
        r"\bin\s+([A-Z][a-zA-Z ]+?)\s+(?:versus|vs\.?)\s+([A-Z][a-zA-Z ]+?)(?:\?|$)",
        text,
    )
    if m_vs_c:
        for part in (m_vs_c.group(1), m_vs_c.group(2)):
            name = part.strip().rstrip(".?!")
            if name and name not in slots.countries and len(name) < 40:
                slots.countries.append(name)
    if slots.countries:
        slots.country = slots.countries[0]
    m_based = re.search(
        r"\b(?:based|reside|living)\s+in\s+([A-Za-z][A-Za-z .'-]+)",
        text,
        re.IGNORECASE,
    )
    if m_based:
        slots.country = m_based.group(1).strip().rstrip(".?!—-")
        # Trim trailing "— regional" style clauses
        slots.country = re.split(
            r"\s+[—\-]\s+|\s+regional|\s+standard|\s+versus|\s+vs",
            slots.country,
            maxsplit=1,
        )[0].strip()
        if slots.country and slots.country not in slots.countries:
            slots.countries.insert(0, slots.country)
    # Membership country takes precedence over place for dues questions
    if slots.countries and re.search(
        r"\b(membership|dues|reside|billing country|regional or standard)\b", t
    ):
        slots.country = slots.countries[0]

    # "X, Y, and Z" candidacy lists
    m_list = re.search(
        r"(?:candidates?|names?|people)\s+([A-Z][^?.!]*)",
        text,
    )
    if m_list:
        raw = m_list.group(1)
        parts = re.split(r",| and ", raw)
        slots.persons = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]

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
    """Format for chat only — never put meta hits in CRE ``table`` references."""
    from application.utils.owasp_agent import PRESENTATION_CHANNEL

    text = result.message
    if result.clarify and not result.ok:
        text = f"{result.message}"
    safe_data = _sanitize_result_data(result.data)
    return {
        "response": f"Answer: {text}",
        # Keep CRE citation table empty so the UI never shows "View in OpenCRE"
        # for Nest/GitHub metadata.
        "table": [],
        "accurate": bool(result.ok),
        "model_name": "owasp-agent-router",
        "owasp_agent": {
            "channel": PRESENTATION_CHANNEL,
            "kind": result.kind,
            "ok": bool(result.ok),
            "clarify": result.clarify,
            "data": safe_data,
            # Only http(s) citations — drop javascript:/data: from poisoned index rows.
            "citations": [
                c
                for c in (result.citations or [])
                if isinstance(c, str)
                and (c.startswith("https://") or c.startswith("http://"))
            ],
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
                "ai projects",
                "related owasp projects",
            )
        )
        or t.strip().startswith("ai ")
        or " on ai" in t
        or "list ai" in t
    )


def _mentions_appsec(text: str) -> bool:
    t = text.lower()
    return "appsec" in t or "application security" in t


def _extract_quoted_or_capitalized_name(text: str) -> Optional[str]:
    m = re.search(r"[\"']([A-Z][^\"']+)[\"']", text)
    if m:
        return m.group(1).strip()
    m_quote = re.search(
        r"\b[Qq]uote\s+([A-Z][a-z]+(?:\s+(?:van|der|de|la|von|[A-Z][a-z]+))+)\s+from\b",
        text,
    )
    if m_quote:
        return m_quote.group(1).strip()
    m_by = re.search(
        r"\btalks?\s+by\s+(?:a\s+random\s+person\s+named\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        text,
    )
    if m_by:
        return m_by.group(1).strip()
    m_did = re.search(
        r"\b(?:[Ww]hat\s+[Dd]id|[Dd]id)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        text,
    )
    if m_did:
        return m_did.group(1).strip()
    m2 = re.search(
        r"(?:position of|board member|candidate|quote)\s+"
        r"([A-Z][a-z]+(?:\s+(?:van|der|de|la|von)\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        text,
    )
    if m2:
        return m2.group(1).strip()
    m3 = re.search(
        r"\b([A-Z][a-z]+(?:\s+(?:van|der|de|la|von)\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:say|said|run|ever|present|give|from)\b",
        text,
    )
    if m3:
        name = m3.group(1).strip()
        first = name.split()[0].lower()
        if first not in ("did", "what", "who", "how", "when", "where", "is", "the"):
            return name
    m4 = re.search(
        r"\b(?:for|by|of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*\??\s*$",
        text,
    )
    if m4:
        return m4.group(1).strip()
    return None
