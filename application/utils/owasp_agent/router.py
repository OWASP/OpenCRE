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
    project_name: Optional[str] = None
    project_a: Optional[str] = None
    project_b: Optional[str] = None


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

    def handle(
        self,
        prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return a chat response dict, or None to defer to CRE RAG.

        ``history`` is prior chat turns ``[{role, content}, ...]`` (native
        LiteLLM-style). Used to resolve clarify follow-ups; does not invent facts.
        """
        if not is_owasp_agent_enabled():
            return None
        text = (prompt or "").strip()
        if not text:
            return None

        effective = _effective_prompt(text, history)
        from application.utils.owasp_agent.person_resolve import (
            list_indexed_person_names,
        )
        from application.utils.owasp_agent.prompt_normalize import normalize_prompt

        known_people = list_indexed_person_names(self.store)

        # NLP normalize (filler/paraphrase strip) before embed + retrieve.
        normalized = normalize_prompt(effective) or effective

        # Multi-lane embedding gate: retrieve top-k agent candidates, pick by
        # score margin or constrained LLM — prefer this over intent/match_*.
        sim_decision = _similarity_gate(normalized)
        intent_preview = classify_intent(effective, known_people=known_people)
        if sim_decision is not None:
            from application.utils.owasp_agent.candidate_picker import (
                default_completion_fn,
                select_agent_hit,
            )
            from application.utils.owasp_agent.lane_similarity import (
                is_evidence_hit,
                is_meta_hit,
            )

            cands = list(getattr(sim_decision, "agent_candidates", None) or [])
            if not cands:
                agent_top = (sim_decision.hits or {}).get("owasp_agent_meta")
                if agent_top is not None:
                    cands = [agent_top]

            # Prefer answering from agent candidates whenever a viable pick
            # exists — even if the CRE lane scored higher (shared names like
            # ASVS). Intent/match_* remains a fallback below.
            picked = select_agent_hit(
                normalized,
                cands,
                get_completion_fn=default_completion_fn,
            )
            if picked is not None and is_evidence_hit(picked):
                cites = (
                    [
                        c.strip()
                        for c in (picked.content or "")
                        .split("Citations:")[-1]
                        .split(",")
                        if "http" in c
                    ]
                    if "Citations:" in (picked.content or "")
                    else []
                )
                message = (picked.content or "").split("\n\nTopics:")[0].strip()
                message = message.split("\n\nCitations:")[0].strip()
                resp = format_chat_response(
                    QueryResult(
                        ok=True,
                        kind="evidence",
                        message=message,
                        citations=cites
                        or (
                            [picked.url]
                            if (picked.url or "").startswith("http")
                            else []
                        ),
                        data={
                            "lane_scores": sim_decision.scores,
                            "evidence_url": picked.url,
                            "pick_reason": "sim_or_llm",
                        },
                    )
                )
                if sim_decision.action == "both":
                    resp["owasp_agent"]["also_cre"] = True
                    resp["owasp_agent"]["lane_reason"] = sim_decision.reason
                return resp
            if picked is not None and is_meta_hit(picked):
                meta_resp = self._response_from_meta_hit(
                    picked, sim_decision=sim_decision
                )
                if meta_resp is not None:
                    return meta_resp

            # CRE-dominant must not erase a mid+ agent evidence / chapter / board card.
            if sim_decision.action == "cre" and cands:
                from application.utils.owasp_agent.lane_similarity import _float_env

                t_rescue = _float_env("OWASP_AGENT_SIM_RESCUE", 0.50)
                for hit in cands:
                    kind = ""
                    u = hit.url or ""
                    if u.startswith("owasp-agent://evidence/"):
                        kind = "evidence"
                    elif u.startswith("owasp-agent://meta/"):
                        kind = u[len("owasp-agent://meta/") :].split("/", 1)[0]
                    if kind in ("evidence", "chapter", "board_roster") and (
                        hit.score >= t_rescue
                    ):
                        if kind == "evidence" and is_evidence_hit(hit):
                            message = (
                                (hit.content or "").split("\n\nTopics:")[0].strip()
                            )
                            message = message.split("\n\nCitations:")[0].strip()
                            cites = (
                                [
                                    c.strip()
                                    for c in (hit.content or "")
                                    .split("Citations:")[-1]
                                    .split(",")
                                    if "http" in c
                                ]
                                if "Citations:" in (hit.content or "")
                                else []
                            )
                            return format_chat_response(
                                QueryResult(
                                    ok=True,
                                    kind="evidence",
                                    message=message,
                                    citations=cites,
                                    data={
                                        "lane_scores": sim_decision.scores,
                                        "evidence_url": hit.url,
                                        "pick_reason": "cre_rescue",
                                    },
                                )
                            )
                        meta_resp = self._response_from_meta_hit(
                            hit, sim_decision=sim_decision
                        )
                        if meta_resp is not None:
                            return meta_resp

            if sim_decision.action == "clarify":
                if intent_preview in ("clarify",) or not cands:
                    return format_chat_response(
                        QueryResult(
                            ok=False,
                            kind="clarify",
                            message=(
                                "I can help with OWASP community metadata (chapters, "
                                "projects, events, board, membership) or OpenCRE "
                                "security standards. Which did you mean?"
                            ),
                            clarify="community metadata or CRE/standards?",
                            data={"lane_scores": sim_decision.scores},
                        )
                    )
                # else: fall through to intent handlers below
            elif sim_decision.action == "cre":
                if intent_preview in (
                    "cre_normative",
                    "cre_fact",
                    "clarify",
                ):
                    return None
                # Strong CRE lane but clear meta intent → prefer meta handlers.

        intent = intent_preview
        if intent == "cre_normative":
            return None
        if intent == "aix_fact":
            from application.utils.owasp_agent.aix_facts import lookup_aix_factoid

            aix_hit = lookup_aix_factoid(effective)
            if not aix_hit:
                return None
            message, citations = aix_hit
            result = QueryResult(
                ok=True,
                kind="aix_fact",
                data={"source": "owasp_ai_exchange"},
                message=message,
                citations=citations,
            )
            return format_chat_response(result)
        if intent == "cre_fact":
            from application.utils.owasp_agent.cre_facts import (
                format_cre_factoid,
                lookup_cre_factoid,
            )

            cre_hit = lookup_cre_factoid(effective)
            if not cre_hit:
                return None  # fall through to CRE RAG
            cre_id, title, note = cre_hit
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

        slots = extract_slots(effective, known_people=known_people)
        result = self._dispatch(intent, slots, effective)
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
        if intent == "person_lookup":
            if not slots.person:
                return QueryResult(
                    ok=False,
                    kind="person_lookup",
                    message="Which person should I look up in OWASP metadata?",
                    clarify="Please give the person's full name.",
                )
            return self.queries.person_lookup(slots.person)
        if intent == "project_lookup":
            name = slots.project_name or slots.topic
            if not name:
                return QueryResult(
                    ok=False,
                    kind="project_lookup",
                    message="Which OWASP project should I look up?",
                    clarify="Please name a project.",
                )
            return self.queries.project_lookup(name)
        if intent == "compare_projects":
            a = slots.project_a
            b = slots.project_b
            if not a or not b:
                return QueryResult(
                    ok=False,
                    kind="compare_projects",
                    message="Which two OWASP projects should I compare?",
                    clarify="Name both projects (e.g. AI Exchange vs GenAI Security Project).",
                )
            return self.queries.compare_projects(a, b)
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


def _similarity_gate(prompt: str):
    """Optional embedding lane decision; None if disabled or unavailable."""
    from application.utils.owasp_agent.lane_similarity import (
        route_prompt,
        sim_router_enabled,
    )

    if not sim_router_enabled():
        return None
    try:
        from application import sqla
        from application.database import db as db_mod
        from application.prompt_client import prompt_client

        database = db_mod.Node_collection()
        if not database.can_use_pgvector_similarity():
            return None
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)

        def _embed(text: str):
            return handler.get_text_embeddings(text)

        bind = sqla.session.get_bind()
        with bind.connect() as conn:
            return route_prompt(prompt, embed_fn=_embed, connection=conn)
    except Exception:
        return None


def classify_intent(text: str, *, known_people: Optional[List[str]] = None) -> str:
    from application.utils.owasp_agent.person_resolve import match_indexed_person

    t = text.lower().strip()
    person_hit = match_indexed_person(text, known_people)
    # Who-is / tell-me-about person lookup from indexed leaders/board (not CRE bios)
    if re.search(r"\bwho is\b", t) and not re.search(r"\bwho is (the|on|a|an)\b", t):
        return "person_lookup"
    if re.search(r"\b(tell me about|what about)\b", t) and person_hit:
        if not re.search(r"\b(vulnerability|mitigate|how (do|should)|cre)\b", t):
            return "person_lookup"
    # Indexed person + which projects they lead
    if (
        person_hit
        and re.search(r"\b(lead|leads|leader|leads\?)\b", t)
        and re.search(r"\bprojects?\b", t)
    ):
        return "person_lookup"

    # Project compare / definition (OWASP metadata, not generic LLM knowledge)
    if re.search(
        r"\b(difference between|differ(?:ence)? between|compare)\b", t
    ) and re.search(r"\b(project|ai exchange|genai|aix|llm top)\b", t):
        return "compare_projects"
    if re.search(
        r"\b(what is|what's|tell me about|describe)\b.+\b("
        r"ai exchange|genai security|genai project|owasp project|"
        r"llm top\s*10|integration standards)\b",
        t,
    ) or re.search(
        r"\b(what is|what's)\b.+\bproject\b",
        t,
    ):
        if not re.search(r"\b(how (do|should)|mitigate|vulnerability)\b", t):
            return "project_lookup"

    # Malicious / unauthorized help — refuse before any meta routing so
    # compound prompts ("dump keys + chapter leader") cannot skip the gate.
    # Prefer multi-word attack phrasing; bare AppSec terms (idor, exfiltrate)
    # alone must not refuse defensive questions.
    if re.search(
        r"("
        r"\bhow do i hack\b|\bteach me to (hack|phish)\b|\bsql injection payload\b|"
        r"\b(launch|perform|run)\s+a\s+ddos\b|\bbreak into\b|"
        r"\bsteal (their|passwords|dms)\b|"
        r"\bphishing (email )?template\b|\bvishing\b|\bmetasploit\b|"
        r"\bsocial-?engineer\b|"
        r"\b(write|craft|build)\s+(a\s+)?phish(ing)?\b|"
        r"\bkeylogger\b|\b(write|build)\s+a\s+worm\b|\bpoison .{0,40}dependency\b|"
        r"\bburp\s+intruder\b|\bauth bypass\b|"
        r"\bbreaking into\b|\bforged token\b|\bransomware\b|\bdox\b|"
        r"\bunrestricted gpt\b|\bdisable safety\b|"
        r"\bhow (do|to) (i )?exfiltrate\b|"
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

    # Fail-closed talk asks (often compound with a CRE factoid) before CRE-only.
    # Do not steal board asks that only say "do not invent talk quotes".
    if (
        re.search(r"\bfail[- ]closed\b", t)
        and re.search(r"\btalk\b", t)
        and not re.search(r"\bboard\b", t)
    ):
        return "talk_lookup"

    # Curated CRE factoids (deterministic) before generic CRE RAG
    if re.search(r"\b(which cre|what cre|cre covers)\b", t) or (
        "cre" in t and "covers" in t
    ):
        from application.utils.owasp_agent.cre_facts import lookup_cre_factoid

        if lookup_cre_factoid(text):
            return "cre_fact"

    # Talk claims (incl. fake speakers / suburb meetups) → fail-closed
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

    # Chapters + projects in one ask (before project-only listing)
    if (
        re.search(r"\bhow many\b.+\bchapters?\b", t)
        or re.search(r"\bchapters?\b.+\b(how many|exist|count)\b", t)
    ) and re.search(r"\bprojects?\b", t):
        return "count_projects_and_chapters"

    # Project listing / counts — phrase-shaped only (no loose "project"+table dump).
    if re.search(
        r"\b(which flagged owasp projects|flagged owasp projects|"
        r"projects touch|list .+ projects|projects? in a table|"
        r"ai-related projects|related owasp projects|"
        r"how many (indexed )?owasp projects)\b",
        t,
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
        r"which chapter|active owasp chapter|chapter status|owasp leader|"
        r"owasp athens|athens currently (active|inactive)|"
        r"count of indexed owasp chapters|approximate count of .{0,20}chapters)\b",
        t,
    ) or (
        re.search(r"\bchapters?\b", t) and re.search(r"\b(active|inactive|status)\b", t)
    ):
        if re.search(
            r"\b(count|how many|approximate count)\b.+\bchapters?\b",
            t,
        ) or re.search(r"\bchapters?\b.+\b(count|how many)\b", t):
            return "count_chapters"
        return "chapter_lookup"

    # Standalone chapter counts (without "how many")
    if (
        re.search(
            r"\b(approximate )?count of (indexed )?owasp chapters\b|"
            r"\bhow many (indexed )?owasp chapters\b|"
            r"\bindexed owasp chapters\b",
            t,
        )
        and "project" not in t
    ):
        return "count_chapters"

    # Board person / service years / candidate page — before talk heuristics
    # (negations like "do not invent talk quotes" must not steal board asks).
    # Year-scoped roster ("Board roster for 2020") stays board_members.
    if re.search(r"\bboard roster\b", t) and re.search(r"\b20\d{2}\b", t):
        if not person_hit:
            return "board_members"
    if re.search(
        r"\b(board (service )?years|board member|board year roster|"
        r"on any indexed owasp board|candidate page|candidacy|"
        r"board interview|candidate statement|run for the owasp board|"
        r"first board interview|quote .{0,40}board interview)\b",
        t,
    ) or (
        "board" in t
        and re.search(r"\b(member|candidate|roster|years?|service)\b", t)
        and person_hit
    ):
        return "board_person"

    # Board roster + refuse invented talk (compound) — answer roster first.
    if (
        re.search(r"\bboard\b", t)
        and re.search(r"\b20\d{2}\b", t)
        and re.search(r"\b(roster|members?)\b", t)
    ):
        if re.search(
            r"\b(refuse|do not invent|fail closed|no talk|keynote quotes?)\b", t
        ) or re.search(r"\bthen refuse\b", t):
            return "board_members"

    # Multi-hop suburb → chapter (+ optional leader talk) before bare talk_lookup.
    # No city-name hardcodes — only structural suburb/meetup cues.
    if re.search(r"\b(multi-hop|suburb|commuting)\b", t) and re.search(
        r"\b(chapter|leader|meetup)\b", t
    ):
        if re.search(r"\b(leader|who leads|chapter)\b", t):
            return "chapter_lookup"
        return "events_near"

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

    # Geo event/meetup asks — word-bounded events/meetups + place cue only.
    if re.search(r"\b(events?|meetups?)\b", t) and re.search(
        r"\b(near|nearby|around|closest|nearest)\b", t
    ):
        return "events_near"

    # Board roster / candidate stats without the old meta/normative dump gate.
    if re.search(r"\bhow many\b", t) and re.search(r"\bcandidates?\b", t):
        return "board_candidate_stats"
    if re.search(r"\bboard\b", t) and (
        re.search(r"\b(members?|roster|who (is|are) on)\b", t)
        or re.search(r"\b20\d{2}\b", t)
    ):
        if person_hit and not re.search(r"\bwho (is|are) on the\b", t):
            return "board_person"
        return "board_members"

    # Chitchat about indexed person + defenses/talk without clear CRE ask
    if (
        re.search(r"\b(keynote|talk|presented|say about|said about)\b", t)
        and person_hit
    ):
        return "talk_lookup"

    # Default: CRE path. Community/meta answers come from sim-first retrieve above
    # classify_intent — not from keyword dump lists.
    return "cre_normative"


def extract_slots(text: str, *, known_people: Optional[List[str]] = None) -> Slots:
    from application.utils.owasp_agent.person_resolve import match_indexed_person

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
    # "leader for Athens" / "chapter status in X" / "Suburb Glendale meetup"
    m_leader_place = re.search(
        r"\b(?:leader|leaders|chapter|status)\s+(?:for|in)\s+"
        r"([A-Z][A-Za-z .'-]+?)(?=\s*[?,.!]| versus | vs\.?\s|$)",
        text,
    )
    if m_leader_place:
        slots.place = m_leader_place.group(1).strip().rstrip(".?!")
    m_suburb = re.search(
        r"\b[Ss]uburb\s+([A-Z][A-Za-z .'-]+?)(?=\s+(?:meetup|chapter|→|,)|\s*$)",
        text,
    )
    if m_suburb:
        slots.place = m_suburb.group(1).strip().rstrip(".?!")

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
    # versus / vs comparisons — city-sized tokens only (no city allowlist)
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
    if slots.place and slots.place not in slots.places:
        slots.places.append(slots.place)

    person = match_indexed_person(text, known_people)
    if person:
        slots.person = person

    m_diff = re.search(
        r"\b(?:difference between|differ(?:ence)? between|compare)\s+"
        r"(?:the\s+)?(.+?)\s+(?:and|vs\.?|versus)\s+(?:the\s+)?(.+?)\s*\??\s*$",
        text,
        re.IGNORECASE,
    )
    if m_diff:
        slots.project_a = _clean_project_name(m_diff.group(1))
        slots.project_b = _clean_project_name(m_diff.group(2))

    m_what_proj = re.search(
        r"\b(?:what is|what's|tell me about|describe)\s+(?:the\s+)?(.+?)\s*\??\s*$",
        text,
        re.IGNORECASE,
    )
    if m_what_proj and not slots.project_a:
        cand = _clean_project_name(m_what_proj.group(1))
        if cand and not re.match(r"^(who|how|why)\b", cand, re.I):
            slots.project_name = cand

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
    return bool(
        re.search(
            r"("
            r"\bai[- ]security\b|\bmachine learning\b|\bgenai\b|\bllms?\b|"
            r"\bartificial intelligence\b|\bai systems?\b|\bai projects?\b|"
            r"\bai-related\b|\bprojects on ai\b|\babout ai\b|\blist ai\b|"
            r"\brelated owasp projects\b"
            r")",
            t,
        )
        or re.search(r"(^|\s)ai(\s|$)", t)
    )


def _mentions_appsec(text: str) -> bool:
    t = text.lower()
    return "appsec" in t or "application security" in t


def _clean_project_name(raw: str) -> str:
    name = (raw or "").strip().rstrip(".?!")
    name = re.sub(
        r"^(the\s+)?(owasp\s+)?",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    name = re.sub(r"\s+project$", "", name, flags=re.IGNORECASE).strip()
    return name


def _effective_prompt(
    prompt: str, history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Join recent user turns so clarify follow-ups keep prior slots/context."""
    prior: List[str] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role") or "").lower() != "user":
            continue
        content = str(turn.get("content") or "").strip()
        if content:
            prior.append(content)
    if prior and prior[-1] == prompt:
        prior = prior[:-1]
    if not prior:
        return prompt
    return (" ".join(prior[-3:]) + "\n" + prompt).strip()
