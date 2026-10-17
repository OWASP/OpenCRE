"""Intent router + clarification slots for the OWASP agent chat extension."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


# Intents with structured slots — do not let a mismatched sim meta card win.
_STRUCTURED_INTENTS = frozenset(
    {
        "events_near",
        "board_members",
        "board_person",
        "board_candidate_stats",
        "project_lookup",
        "compare_projects",
        "person_lookup",
        "membership",
        "chapter_lookup",
        "count_chapters",
        "count_projects",
        "count_projects_and_chapters",
        "talk_lookup",
        "cre_fact",
        "cre_community_bait",
        "project_and_board",
        "clarify",
        "refuse_malicious",
    }
)

# Well-known project tokens that are not the foundation board.
_PROJECT_BOARD_ALIASES = (
    "asvs",
    "masvs",
    "samm",
    "juice shop",
    "juiceshop",
    "zap",
    "top ten",
    "top-ten",
    "top 10",
    "ai exchange",
    "aix",
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

    def _response_from_meta_hit(
        self,
        agent_hit: Any,
        *,
        sim_decision: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Answer from a similarity hit whose URL is ``owasp-agent://meta/...``."""
        url = str(getattr(agent_hit, "url", "") or "")
        if not url.startswith("owasp-agent://meta/"):
            return None
        parts = url[len("owasp-agent://meta/") :].split("/")
        if len(parts) < 2:
            return None
        kind = parts[0].strip().lower()
        key = parts[1].strip()
        if not kind or not key:
            return None
        result: Optional[QueryResult] = None
        if kind == "chapter":
            result = self.queries.chapter_lookup(place=key.replace("-", " "))
        elif kind == "project":
            result = self.queries.project_lookup(key.replace("-", " "))
        elif kind == "board_roster":
            result = self.queries.corpus_entity("board_roster", key)
            if not result.ok:
                # Fall back to embed prose already on the hit.
                message = str(getattr(agent_hit, "content", "") or "").strip()
                if message:
                    result = QueryResult(
                        ok=True,
                        kind="meta_board_roster",
                        message=message.split("\nTopics:")[0].strip(),
                        data={"meta_url": url, "key": key},
                    )
        elif kind in ("board_member", "board_candidate"):
            # Corpus card from embed text — no board_* query assembly.
            message = str(getattr(agent_hit, "content", "") or "").strip()
            if message:
                result = QueryResult(
                    ok=True,
                    kind=f"meta_{kind}",
                    message=message.split("\nTopics:")[0].strip(),
                    data={"meta_url": url, "key": key},
                )
        elif kind in ("project_leader", "person"):
            name = key.replace("-", " ")
            content = str(getattr(agent_hit, "content", "") or "")
            for line in content.splitlines():
                if line.lower().startswith("owasp ") and ":" in line:
                    name = line.split(":", 1)[1].strip() or name
                    break
            result = self.queries.person_lookup(name)
        elif kind == "event":
            # Fall back to content card; events_near needs geo slots.
            message = str(getattr(agent_hit, "content", "") or "").strip()
            if message:
                result = QueryResult(
                    ok=True,
                    kind="event_meta",
                    message=message,
                    data={"meta_url": url, "key": key},
                )
        elif kind == "membership_country":
            result = self.queries.membership_info(country=key.replace("-", " "))
        if result is None:
            message = str(getattr(agent_hit, "content", "") or "").strip()
            if not message:
                return None
            result = QueryResult(
                ok=True,
                kind=f"meta_{kind}",
                message=message.split("\nTopics:")[0].strip(),
                data={"meta_url": url, "key": key},
            )
        resp = format_chat_response(result)
        if sim_decision is not None:
            resp.setdefault("owasp_agent", {})
            resp["owasp_agent"]["lane_scores"] = getattr(sim_decision, "scores", None)
            resp["owasp_agent"]["lane_reason"] = getattr(sim_decision, "reason", None)
            if getattr(sim_decision, "action", None) == "both":
                resp["owasp_agent"]["also_cre"] = True
        return resp

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
                is_structure_ask,
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
            structure_ask = is_structure_ask(normalized)

            # Slot-heavy intents (board year, events near, ambiguous chapter…)
            # must not be overridden by a mismatched sim meta card.
            early_slots = extract_slots(effective)

            def _allow_sim_meta(hit: Any) -> bool:
                kind, key = _meta_kind_key(getattr(hit, "url", "") or "")
                if not kind:
                    return True
                return _sim_meta_ok_for_intent(
                    intent_preview, kind, key, effective, early_slots
                )

            if (
                picked is not None
                and is_evidence_hit(picked)
                and intent_preview
                not in (
                    "events_near",
                    "board_members",
                    "clarify",
                    "cre_community_bait",
                    "project_and_board",
                )
            ):
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
            if picked is not None and is_meta_hit(picked) and _allow_sim_meta(picked):
                # Fail-closed: never answer level/layer/maturity asks via Nest
                # project_lookup (Leaders: / indexed OWASP project).
                meta_kind = ""
                u = picked.url or ""
                if u.startswith("owasp-agent://meta/"):
                    meta_kind = u[len("owasp-agent://meta/") :].split("/", 1)[0]
                if structure_ask and meta_kind == "project":
                    return None
                meta_resp = self._response_from_meta_hit(
                    picked, sim_decision=sim_decision
                )
                if meta_resp is not None:
                    return meta_resp
            elif structure_ask and not any(is_evidence_hit(h) for h in cands):
                # Structure ask, no evidence in top-k, no viable pick → defer.
                return None

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
                        if not _allow_sim_meta(hit) and kind != "evidence":
                            continue
                        if kind == "evidence" and is_evidence_hit(hit):
                            if intent_preview in (
                                "events_near",
                                "board_members",
                                "clarify",
                                "cre_community_bait",
                                "project_and_board",
                            ):
                                continue
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
        if intent == "cre_fact":
            # Metadata facts by CRE id only — no keyword factoid gate.
            from application.utils.owasp_agent.node_facts import (
                extract_cre_id_from_text,
                facts_for_cre_id,
                format_facts_message,
            )

            cre_id = extract_cre_id_from_text(effective)
            facts = facts_for_cre_id(cre_id or "")
            if not facts:
                return None  # fall through to CRE RAG
            message, citations = format_facts_message(facts)
            if not message:
                return None
            result = QueryResult(
                ok=True,
                kind="cre_fact",
                data={"cre_id": cre_id, "facts": facts},
                message=message,
                citations=citations
                or ([f"https://opencre.org/cre/{cre_id}"] if cre_id else []),
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
            topic = slots.topic
            if topic is None and _mentions_ai(text):
                topic = "ai_security"
            if topic is None and _mentions_appsec(text):
                topic = "appsec"
            list_mode = slots.list_mode or bool(
                re.search(r"\b(list|table|which projects)\b", text.lower())
            )
            projects = self.queries.count_projects(
                topic=topic, list_mode=list_mode and topic is not None
            )
            ch_n = (chapters.data or {}).get("count")
            pr_n = (projects.data or {}).get("count")
            if ch_n is None:
                return QueryResult(
                    ok=False,
                    kind="count_projects_and_chapters",
                    message="I could not read the chapter count from the index.",
                )
            if not projects.ok and topic:
                # Still report chapters; surface project clarify/fail in the message.
                return QueryResult(
                    ok=True,
                    kind="count_projects_and_chapters",
                    data={"chapters": ch_n, "projects": None, "topic": topic},
                    message=(
                        f"The local index has {ch_n} OWASP chapters. "
                        f"{projects.message}"
                    ),
                    citations=list(chapters.citations or []),
                )
            if pr_n is None:
                pr_n = (projects.data or {}).get("count")
            msg = f"The local index has {ch_n} OWASP chapters"
            if topic and projects.ok:
                msg += f" and {pr_n} projects matching topic {topic!r}"
            elif projects.ok:
                msg += f" and {pr_n} OWASP projects"
            msg += "."
            if list_mode and projects.ok and projects.message:
                # Append the project table / listing from count_projects.
                detail = projects.message
                if detail and not detail.startswith("Answer:"):
                    msg = f"{msg}\n\n{detail}"
            return QueryResult(
                ok=True,
                kind="count_projects_and_chapters",
                data={
                    "chapters": ch_n,
                    "projects": pr_n,
                    "topic": topic,
                    "project_data": projects.data,
                },
                message=msg,
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
        if intent in ("board_members", "board_person", "board_candidate_stats"):
            # Board answers come from corpus ontology cards (board_roster), not
            # assembled in query methods. Materialize cards if the index has
            # raw members but no roster yet (local tests / fresh sync).
            from application.utils.owasp_agent.meta_embeddings import (
                materialize_board_ontology,
            )

            try:
                materialize_board_ontology(self.store)
            except Exception:
                pass
            if slots.person:
                # Named person: prefer person_lookup (leaders + board rows).
                return self.queries.person_lookup(slots.person)
            years = slots.years or ([slots.year] if slots.year is not None else [])
            if years:
                hit = self.queries.corpus_entity("board_roster", str(years[0]))
                if hit.ok:
                    return hit
                # Explicit year with no card — fail closed (do not substitute latest).
                members = self.queries.board_members(int(years[0]))
                if members.ok:
                    return members
                return QueryResult(
                    ok=False,
                    kind="board_members",
                    message=(
                        f"No OWASP board roster is indexed for year {years[0]} "
                        "(fail closed). I will not substitute another year's members."
                    ),
                )
            return self.queries.corpus_entity("board_roster", "overview")
        if intent == "project_and_board":
            proj_name = slots.project_name or ""
            # Slot extract may swallow "… AND who is on the board".
            if " and " in proj_name.lower():
                proj_name = re.split(r"\s+and\s+", proj_name, maxsplit=1, flags=re.I)[
                    0
                ].strip()
            if not proj_name or not _mentions_known_project(proj_name):
                if re.search(r"\bjuice\s*shop\b|\bjuiceshop\b", text, re.I):
                    proj_name = "Juice Shop"
                elif re.search(r"\basvs\b", text, re.I):
                    proj_name = "ASVS"
                else:
                    proj_name = proj_name or "Juice Shop"
            proj = self.queries.project_lookup(proj_name)
            board = self.queries.corpus_entity("board_roster", "overview")
            parts = []
            cites: List[str] = []
            if proj.ok:
                parts.append(proj.message)
                cites.extend(proj.citations or [])
            if board.ok:
                parts.append(board.message)
                cites.extend(board.citations or [])
            if not parts:
                return QueryResult(
                    ok=False,
                    kind="project_and_board",
                    message="I could not find Juice Shop leaders or board roster in the index.",
                )
            return QueryResult(
                ok=True,
                kind="project_and_board",
                data={
                    "project": (proj.data or {}).get("project") if proj.ok else None,
                    "board": (board.data or {}).get("entity") if board.ok else None,
                },
                message=" ".join(parts),
                citations=list(dict.fromkeys(cites)),
            )
        if intent == "cre_community_bait":
            name = slots.project_name or slots.place or slots.topic
            if name and (
                "chapter" in text.lower()
                or (slots.place and "project" not in text.lower())
            ):
                ch = self.queries.chapter_lookup(
                    place=slots.place, places=slots.places or None
                )
                base = ch.message if ch.ok else f"OWASP community entity {name!r}"
                return QueryResult(
                    ok=True,
                    kind="cre_community_bait",
                    data=ch.data if ch.ok else {"name": name},
                    message=(
                        f"{base} OWASP chapters and meetup policies are community "
                        "metadata, not Common Requirements (CREs) — there is no CRE ID "
                        "that 'covers' a chapter meetup policy."
                    ),
                    citations=list(ch.citations or []) if ch.ok else [],
                )
            proj = self.queries.project_lookup(name or "Juice Shop")
            base = proj.message if proj.ok else f"{name or 'That OWASP project'}"
            return QueryResult(
                ok=True,
                kind="cre_community_bait",
                data=proj.data if proj.ok else {"name": name},
                message=(
                    f"{base} OWASP projects are community/metadata entities, not CRE "
                    "nodes — there is no single CRE ID that maps an entire project."
                ),
                citations=list(proj.citations or []) if proj.ok else [],
            )
        if intent == "clarify":
            return QueryResult(
                ok=False,
                kind="clarify",
                message=(
                    "Which OWASP chapter or city do you mean? "
                    "I need a place name to look up chapter leaders or the next meetup."
                ),
                clarify="Please name a city or chapter (e.g. London, Berlin).",
            )
        if intent == "chapter_lookup":
            places = list(slots.places or [])
            if slots.place and slots.place not in places:
                places = [slots.place] + places
            # Multi-city compare / negation: look up all named places.
            if len(places) >= 2:
                return self.queries.chapter_lookup(places=places)
            if not places:
                return QueryResult(
                    ok=False,
                    kind="clarify",
                    message=(
                        "Which OWASP chapter or city should I look up? "
                        "Please name one (e.g. London, Berlin)."
                    ),
                    clarify="Please name a city or chapter.",
                )
            return self.queries.chapter_lookup(place=places[0], places=places)
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
            talk = self.queries.talk_lookup(person=slots.person, topic=slots.topic)
            # Compound: fail-closed talk + CRE id with metadata facts (no keywords).
            from application.utils.owasp_agent.node_facts import (
                extract_cre_id_from_text,
                facts_for_cre_id,
                format_facts_message,
            )

            cre_id = extract_cre_id_from_text(text)
            facts = facts_for_cre_id(cre_id or "") if cre_id else {}
            if facts and talk.ok:
                cre_msg, cre_cites = format_facts_message(facts)
                if cre_msg:
                    return QueryResult(
                        ok=True,
                        kind="talk_and_cre",
                        data={
                            "talk": talk.data,
                            "cre_id": cre_id,
                            "facts": facts,
                        },
                        message=f"{talk.message} Separately: {cre_msg}",
                        citations=list(
                            dict.fromkeys(
                                list(talk.citations or [])
                                + list(cre_cites)
                                + (
                                    [f"https://opencre.org/cre/{cre_id}"]
                                    if cre_id
                                    else []
                                )
                            )
                        ),
                    )
            return talk
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
            from application.utils.owasp_agent.candidate_picker import is_structure_ask

            # Fail-closed: structural level/layer/maturity asks must not Nest-steal.
            if is_structure_ask(text):
                return QueryResult(
                    ok=False,
                    kind="clarify",
                    message=(
                        "I do not have curated structure evidence for that question "
                        "in the agent index. Try again after evidence is seeded, "
                        "or ask via CRE/standards tools."
                    ),
                )
            name = slots.project_name or slots.topic
            if not name:
                return QueryResult(
                    ok=False,
                    kind="project_lookup",
                    message="Which OWASP project should I look up?",
                    clarify="Please name a project.",
                )
            result = self.queries.project_lookup(name)
            if (
                result.ok
                and re.search(r"\bboard\b", text.lower())
                and _mentions_known_project(text)
            ):
                note = (
                    " It does not have a separate foundation board; "
                    "indexed project leaders are listed."
                )
                if "does not have a separate foundation board" not in result.message:
                    result = QueryResult(
                        ok=result.ok,
                        kind=result.kind,
                        data=result.data,
                        message=result.message.rstrip(".") + "." + note,
                        citations=result.citations,
                        clarify=result.clarify,
                    )
            return result
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
        # cre_fact is handled in handle() before _dispatch.
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
    # Strip markdown fences / chat-role wrappers for structural matching.
    t_flat = re.sub(r"[`*\n]+", " ", t)
    t_flat = re.sub(r"\b(user|assistant)\s*:", " ", t_flat)
    t_flat = re.sub(r"\s+", " ", t_flat).strip()

    # Ambiguous chapter/meetup with no place — clarify before sim can invent one.
    if re.search(
        r"\b(who is the chapter leader|chapter leader\b|when is the next meetup|"
        r"next meetup\b)\b",
        t_flat,
    ) and not re.search(
        r"\b(in|near|around|for)\s+[a-z]",
        t_flat,
    ):
        # Allow "London chapter leader" etc. via place cues below.
        if not re.search(
            r"\b(london|berlin|athens|tokyo|paris|nyc|new york|bangalore|"
            r"los angeles|san francisco|seattle|chicago|toronto|sydney)\b",
            t_flat,
        ):
            return "clarify"

    # CRE-bait on community entities (project/chapter) — answer meta, no CRE id.
    if re.search(r"\b(map .+ to (a )?cre|what cre covers|cre covers|cre id)\b", t_flat):
        if re.search(
            r"\b(juice\s*shop|juiceshop|chapter|meetup|asvs|project|berlin|london)\b",
            t_flat,
        ):
            return "cre_community_bait"

    # Dual: project leaders + foundation board in one ask.
    if re.search(r"\b(juice\s*shop|juiceshop|asvs|zap|top\s*ten)\b", t_flat) and (
        re.search(r"\b(leads?|leaders?|who leads)\b", t_flat)
        and re.search(r"\b(owasp )?board\b", t_flat)
        and re.search(r"\b(and|who is on)\b", t_flat)
    ):
        return "project_and_board"

    # Project-named "board members" (ASVS board) → project leaders, not foundation.
    if re.search(r"\bboard\b", t_flat) and re.search(
        r"\b(members?|roster|who (is|are))\b", t_flat
    ):
        if any(alias in t_flat for alias in _PROJECT_BOARD_ALIASES):
            return "project_lookup"

    # GitHub-style www-project-* slug / what-is project.
    if re.search(r"\bwww-project-[a-z0-9-]+\b", t_flat) or re.search(
        r"\bowasp/[a-z0-9._/-]+\b", t_flat
    ):
        return "project_lookup"

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

    # Project-vs-chapter counts before project-vs-project compares.
    if re.search(r"\b(projects? versus chapters|chapters versus projects)\b", t):
        return "count_projects_and_chapters"
    if (
        "how many" in t
        and re.search(r"\bchapters?\b", t)
        and re.search(r"\bprojects?\b", t)
    ):
        return "count_projects_and_chapters"
    # Chapter compare (London vs Berlin) before project compare.
    if re.search(
        r"\b(difference between|differ(?:ence)? between|compare|"
        r"\bvs\.?\b|versus)\b",
        t_flat,
    ) and re.search(r"\bchapters?\b", t_flat):
        if not re.search(r"\bprojects?\b", t_flat):
            return "chapter_lookup"
    # Project compare / definition — structural phrasing only (no brand lists).
    if re.search(
        r"\b(difference between|differ(?:ence)? between|compare|"
        r"\bvs\.?\b|versus|how do they differ|how they differ)\b",
        t,
    ) and re.search(r"\bprojects?\b", t):
        # "projects versus chapters" already handled; bare chapter compare stays out.
        if (
            re.search(r"\bchapters?\b", t)
            and re.search(r"\bprojects?\b", t)
            and "difference" not in t
        ):
            return "count_projects_and_chapters"
        return "compare_projects"
    if re.search(
        r"\b(what is|what's|describe)\b.+\bowasp project\b", t_flat
    ) or re.search(
        r"\b(what is|what's)\b.+\bproject\b",
        t_flat,
    ):
        if not re.search(r"\b(how (do|should)|mitigate|vulnerability)\b", t_flat):
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

    # CRE id with curated metadata facts (no keyword factoid gate).
    from application.utils.owasp_agent.node_facts import (
        extract_cre_id_from_text,
        facts_for_cre_id,
    )

    cre_id_hint = extract_cre_id_from_text(text)
    if cre_id_hint and facts_for_cre_id(cre_id_hint):
        # Talk + CRE compound stays talk_lookup so handle() can merge both.
        if re.search(r"\btalk\b", t):
            return "talk_lookup"
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

    # Project leaders (incl. "leaders of Top Ten" / "JuiceShop … leaders?").
    if re.search(r"\b(who leads|leaders? (of|for)|project leaders?)\b", t_flat) or (
        re.search(r"\bprojects?\b", t_flat) and re.search(r"\bleaders?\b", t_flat)
    ):
        if re.search(r"\bprojects?\b", t_flat) or _mentions_known_project(t_flat):
            return "project_lookup"

    # Named / what-is OWASP chapter cards (phrase-shaped — not bare "chapter").
    if re.search(
        r"\b(what is|what's|whats|tell me about|describe)\b.{0,60}\bchapters?\b",
        t,
    ):
        return "chapter_lookup"
    if re.search(r"\bowasp\b.{0,40}\bchapters?\b", t) and not re.search(
        r"\b(how many|count of|versus|vs\.?)\b", t
    ):
        return "chapter_lookup"

    # Chapter existence / negation / "chapter in {city}" before general clarify.
    if re.search(r"\bchapters?\b", t) and re.search(
        r"\b(in|near|for|at|around|not exist|does not exist|doesn't exist)\b", t
    ):
        if not re.search(r"\b(how many|count of)\b", t):
            return "chapter_lookup"
    if re.search(
        r"\b(does|is there|any|have).{0,40}\bchapter\b|\bchapter\b.{0,20}\b(exist|active)\b",
        t,
    ):
        return "chapter_lookup"
    if re.search(r"\bwhich .{0,40}chapter .{0,20}not exist\b", t_flat) or re.search(
        r"\bchapter does not exist\b", t_flat
    ):
        return "chapter_lookup"

    # Chapter leader / status / active — chapter cue, or "OWASP leader for {city}".
    if re.search(
        r"\b(chapter leader|leader for (the )?chapter|who leads .{0,20}chapter|"
        r"which chapter|active owasp chapter|chapter status|owasp chapter leader|"
        r"count of indexed owasp chapters|approximate count of .{0,20}chapters)\b",
        t,
    ) or (
        re.search(r"\bchapters?\b", t)
        and re.search(r"\b(active|inactive|status|leaders?|who leads)\b", t)
    ):
        if re.search(
            r"\b(count|how many|approximate count)\b.+\bchapters?\b",
            t,
        ) or re.search(r"\bchapters?\b.+\b(count|how many)\b", t):
            return "count_chapters"
        return "chapter_lookup"
    # "Who is the OWASP leader for Athens?" — city/place leader, not Top Ten.
    if (
        re.search(r"\b(owasp leader|leader for)\b", t_flat)
        and not _mentions_known_project(t_flat)
        and not re.search(r"\bprojects?\b", t_flat)
    ):
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
    ) and not re.search(
        r"\b(board interview|candidate statement|board (service )?years|"
        r"do not invent talk|board roster|refuse to invent)\b",
        t,
    ):
        return "talk_lookup"

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
        if re.search(r"\b(board (service )?years|do not invent talk)\b", t):
            return "board_person"
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
    elif re.search(r"\b(this|current)\s+year\b", t) or re.search(
        r"\bfor this year\b", t
    ):
        # Calendar year in UTC — "this year" must not pick a random sim year card.
        y = datetime.now(timezone.utc).year
        slots.year = y
        slots.years = [y]

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

    # "Compare OWASP London and OWASP Berlin chapters" / "London or Atlantis"
    m_and_ch = re.search(
        r"\b(?:compare\s+)?(?:owasp\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        r"\s+and\s+(?:owasp\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+chapters?\b",
        text,
        re.IGNORECASE,
    )
    if m_and_ch:
        slots.places = [
            m_and_ch.group(1).strip().rstrip(".?!"),
            m_and_ch.group(2).strip().rstrip(".?!"),
        ]
        slots.place = slots.places[0]
    m_or_ch = re.search(
        r"\b(?:does\s+)?not\s+exist\s*:\s*"
        r"([A-Za-z][A-Za-z '-]+?)\s+or\s+([A-Za-z][A-Za-z '-]+?)\s*\??\s*$",
        text,
        re.IGNORECASE,
    )
    if not m_or_ch and re.search(r"\b(not exist|does not exist|doesn't exist)\b", t):
        m_or_ch = re.search(
            r"\b([A-Z][a-zA-Z'-]+)\s+or\s+([A-Z][a-zA-Z'-]+)\b",
            text,
        )
    if m_or_ch:
        a = m_or_ch.group(1).strip().rstrip(".?!")
        b = m_or_ch.group(2).strip().rstrip(".?!")
        # Drop leftover cue words ("chapter", "owasp").
        for city in (a, b):
            low = city.lower()
            if low in ("chapter", "owasp", "the", "a", "an"):
                continue
            if city and city not in slots.places:
                slots.places.append(city)
        if not slots.place and slots.places:
            slots.place = slots.places[0]

    person = match_indexed_person(text, known_people)
    if person:
        slots.person = person
    # "Fail-closed on Spyros … talk" — single given name is enough for fail-closed.
    if not slots.person:
        m_on_talk = re.search(
            r"\bon\s+([A-Z][a-z]{2,})\s+(?:\S+\s+){0,4}talk\b",
            text,
        )
        if m_on_talk:
            slots.person = m_on_talk.group(1).strip()

    m_diff = re.search(
        r"\b(?:difference between|differ(?:ence)? between|compare)\s+"
        r"(?:the\s+)?(.+?)\s+(?:and|vs\.?|versus)\s+(?:the\s+)?(.+?)\s*\??\s*$",
        text,
        re.IGNORECASE,
    )
    if m_diff:
        slots.project_a = _clean_project_name(m_diff.group(1))
        slots.project_b = _clean_project_name(m_diff.group(2))
    if not slots.project_a or not slots.project_b:
        # "AI Exchange project vs GenAI security project — how do they differ?"
        m_vs_proj = re.search(
            r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s*[—–\-:,].*)?\s*$",
            text.strip(),
            re.IGNORECASE,
        )
        if m_vs_proj and re.search(r"\bprojects?\b", text, re.I):
            slots.project_a = _clean_project_name(m_vs_proj.group(1))
            slots.project_b = _clean_project_name(m_vs_proj.group(2))

    m_slug_early = re.search(
        r"\b(?:owasp/)?www-project-([a-z0-9-]+)\b",
        text,
        re.IGNORECASE,
    )
    if m_slug_early and not slots.project_name:
        slots.project_name = m_slug_early.group(1).replace("-", " ")

    m_what_proj = re.search(
        r"\b(?:what is|what's|tell me about|describe)\s+(?:the\s+)?(.+?)\s*\??\s*$",
        text,
        re.IGNORECASE,
    )
    if m_what_proj and not slots.project_a and not slots.project_name:
        cand = _clean_project_name(m_what_proj.group(1))
        if cand and not re.match(r"^(who|how|why|it|this|that|a|an)\b", cand, re.I):
            slots.project_name = cand

    # "Who leads the OWASP Juice Shop project?" / "leaders of OWASP ASVS"
    if not slots.project_name:
        m_leads_proj = re.search(
            r"\b(?:who leads|leaders? (?:of|for)|project leaders? (?:of|for))\s+"
            r"(?:the\s+)?(?:owasp\s+)?(.+?)\s+projects?\b",
            text,
            re.IGNORECASE,
        )
        if not m_leads_proj:
            m_leads_proj = re.search(
                r"\b(?:who leads|leaders? (?:of|for)|project leaders? (?:of|for))\s+"
                r"(?:the\s+)?(?:owasp\s+)?(.+?)\s*\??\s*$",
                text,
                re.IGNORECASE,
            )
        if m_leads_proj:
            cand = _clean_project_name(m_leads_proj.group(1))
            if cand and not re.match(r"^(the|a|an|owasp)$", cand, re.I):
                slots.project_name = cand
        if not slots.project_name:
            m_owasp_proj = re.search(
                r"\bowasp\s+(.+?)\s+project\b",
                text,
                re.IGNORECASE,
            )
            if m_owasp_proj and re.search(r"\b(lead|leader|who)\b", text, re.I):
                cand = _clean_project_name(m_owasp_proj.group(1))
                if cand:
                    slots.project_name = cand
        if not slots.project_name:
            m_slug = re.search(
                r"\b(?:owasp/)?www-project-([a-z0-9-]+)\b",
                text,
                re.IGNORECASE,
            )
            if m_slug:
                slots.project_name = m_slug.group(1).replace("-", " ")
        if not slots.project_name and re.search(r"\bjuiceshop\b|\bjuice\s*shop\b", t):
            slots.project_name = "Juice Shop"
        if not slots.project_name and re.search(r"\basvs\b", t):
            slots.project_name = "ASVS"
        if not slots.project_name and re.search(r"\btop\s*ten\b|\btop\s*10\b", t):
            slots.project_name = "Top Ten"

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


# Capitalized personal names, including multi-particle Dutch/German forms
# (e.g. "Rob van der Veer", "Andrew van der Stock").
_PERSON_NAME_RE = r"[A-Z][a-z]+(?:\s+(?:van|der|de|la|von|[A-Z][a-z]+))+"

_NAME_LEADING_STOPWORDS = frozenset(
    {
        "show",
        "compare",
        "quote",
        "quoting",
        "before",
        "after",
        "when",
        "what",
        "which",
        "whose",
        "did",
        "does",
        "has",
        "have",
        "is",
        "are",
        "was",
        "were",
        "the",
        "and",
        "for",
        "from",
        "with",
        "about",
        "board",
        "nearest",
        "multi",
        "hop",
        "fail",
        "closed",
        "draft",
        "list",
        "how",
        "many",
    }
)


def _name_starts_with_stopword(name: str) -> bool:
    first = (name or "").strip().split()[0].lower() if name else ""
    return first in _NAME_LEADING_STOPWORDS


def _extract_quoted_or_capitalized_name(text: str) -> Optional[str]:
    m = re.search(r"[\"']([A-Z][^\"']+)[\"']", text)
    if m:
        return m.group(1).strip()
    m_who = re.search(r"\b[Ww]ho\s+is\s+(" + _PERSON_NAME_RE + r")\s*\??", text)
    if m_who:
        return m_who.group(1).strip().rstrip(".?!")
    m_about = re.search(
        r"\b(?:[Tt]ell me about|[Ww]hat about)\s+(" + _PERSON_NAME_RE + r")\b",
        text,
    )
    if m_about and not _name_starts_with_stopword(m_about.group(1)):
        return m_about.group(1).strip().rstrip(".?!")
    # "Jeff Williams: board service years…" (colon only — not Name's possessive)
    m_lead = re.search(
        r"^(" + _PERSON_NAME_RE + r")\s*:",
        text.strip(),
    )
    if m_lead and not _name_starts_with_stopword(m_lead.group(1)):
        return m_lead.group(1).strip()
    # Leading name before dash/em-dash ("Rob van der Veer — which projects…")
    m_lead_dash = re.search(
        r"^(" + _PERSON_NAME_RE + r")\s*[—–\-]\s*",
        text.strip(),
    )
    if m_lead_dash and not _name_starts_with_stopword(m_lead_dash.group(1)):
        return m_lead_dash.group(1).strip()
    # Leading name + board / years without requiring colon
    # ("Andrew van der Stock board years — …")
    m_lead_board = re.search(
        r"^(" + _PERSON_NAME_RE + r")\s+board\b",
        text.strip(),
    )
    if m_lead_board and not _name_starts_with_stopword(m_lead_board.group(1)):
        return m_lead_board.group(1).strip()
    # Verb-led extractions before bare possessive (avoids "Show Sam …" as a name).
    m_is = re.search(
        r"\b[Ii]s\s+(" + _PERSON_NAME_RE + r")\s+on\b",
        text,
    )
    if m_is:
        return m_is.group(1).strip()
    m_has = re.search(
        r"\b[Hh]as\s+(" + _PERSON_NAME_RE + r")\s+been\b",
        text,
    )
    if m_has:
        return m_has.group(1).strip()
    m_show = re.search(
        r"\b[Ss]how\s+(" + _PERSON_NAME_RE + r")(?:'s|’s)?\b",
        text,
    )
    if m_show:
        return m_show.group(1).strip()
    m_compare = re.search(
        r"\b[Cc]ompare\s+(" + _PERSON_NAME_RE + r")(?:'s|’s)?\b",
        text,
    )
    if m_compare:
        return m_compare.group(1).strip()
    m_quoting = re.search(
        r"\b(?:quoting|quote)\s+(" + _PERSON_NAME_RE + r")(?:'s|’s)?\b",
        text,
        re.IGNORECASE,
    )
    if m_quoting:
        return m_quoting.group(1).strip()
    # Any possessive Name's … (candidate page, board candidacy, AppSec talk)
    m_possessive = re.search(
        r"\b(" + _PERSON_NAME_RE + r")(?:'s|’s)\b",
        text,
    )
    if m_possessive and not _name_starts_with_stopword(m_possessive.group(1)):
        return m_possessive.group(1).strip()
    m_by = re.search(
        r"\btalks?\s+by\s+(?:a\s+random\s+person\s+named\s+)?("
        + _PERSON_NAME_RE
        + r")\b",
        text,
    )
    if m_by:
        return m_by.group(1).strip()
    m_did = re.search(
        r"\b(?:[Ww]hat\s+[Dd]id|[Dd]id)\s+(" + _PERSON_NAME_RE + r")\b",
        text,
    )
    if m_did:
        return m_did.group(1).strip()
    m2 = re.search(
        r"(?:position of|board member|candidate|quote)\s+(" + _PERSON_NAME_RE + r")",
        text,
    )
    if m2:
        return m2.group(1).strip()
    m3 = re.search(
        r"\b(" + _PERSON_NAME_RE + r")\s+(?:say|said|run|ever|present|give|from)\b",
        text,
    )
    if m3:
        name = m3.group(1).strip()
        first = name.split()[0].lower()
        if first not in ("did", "what", "who", "how", "when", "where", "is", "the"):
            return name
    m4 = re.search(
        r"\b(?:for|by|of)\s+(" + _PERSON_NAME_RE + r")\s*\??\s*$",
        text,
    )
    if m4:
        return m4.group(1).strip()
    return None


def _meta_kind_key(url: str) -> tuple[str, str]:
    """Parse ``owasp-agent://meta/{kind}/{key}/...`` → (kind, key)."""
    u = (url or "").strip()
    if not u.startswith("owasp-agent://meta/"):
        return "", ""
    parts = u[len("owasp-agent://meta/") :].split("/")
    if len(parts) < 2:
        return (parts[0].strip().lower() if parts else ""), ""
    return parts[0].strip().lower(), parts[1].strip()


def _mentions_known_project(text: str) -> bool:
    t = (text or "").lower()
    if any(a in t for a in _PROJECT_BOARD_ALIASES):
        return True
    if re.search(r"\bwww-project-[a-z0-9-]+\b", t):
        return True
    if re.search(r"\bjuiceshop\b|\bjuice\s*shop\b|\btop\s*ten\b|\btop\s*10\b", t):
        return True
    return False


def _sim_meta_ok_for_intent(
    intent: str,
    kind: str,
    key: str,
    text: str,
    slots: Optional[Slots],
) -> bool:
    """Whether a similarity meta hit may answer ``intent`` (else fall through)."""
    intent = (intent or "").strip()
    kind = (kind or "").strip().lower()
    key = (key or "").strip()
    if intent not in _STRUCTURED_INTENTS:
        return True
    if intent in (
        "clarify",
        "refuse_malicious",
        "cre_community_bait",
        "project_and_board",
    ):
        return False
    if intent == "events_near":
        return kind == "event"
    if intent == "board_members":
        if kind != "board_roster":
            return False
        years: List[int] = []
        if slots is not None:
            years = list(slots.years or [])
            if slots.year is not None and slots.year not in years:
                years = [slots.year] + years
        if years:
            return key == str(years[0])
        return key in ("overview", "") or bool(re.fullmatch(r"20\d{2}", key))
    if intent == "board_person":
        return kind in ("board_member", "board_candidate", "person", "project_leader")
    if intent == "chapter_lookup":
        if kind != "chapter":
            return False
        places: List[str] = []
        if slots is not None:
            places = list(slots.places or [])
            if slots.place and slots.place not in places:
                places = [slots.place] + places
        if len(places) >= 2:
            return False
        if not places:
            return False
        target = re.sub(r"[^a-z0-9]+", "-", places[0].lower()).strip("-")
        key_n = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
        return bool(target) and (target in key_n or key_n in target)
    if intent == "project_lookup":
        return kind == "project"
    if intent == "person_lookup":
        return kind in ("person", "project_leader", "board_member", "board_candidate")
    if intent == "membership":
        return kind in ("membership_country", "membership")
    if intent == "compare_projects":
        return False
    if intent.startswith("count_"):
        return False
    if intent == "talk_lookup":
        return False
    if intent == "cre_fact":
        return False
    if intent == "board_candidate_stats":
        return False
    return True


def _clean_project_name(raw: str) -> str:
    name = (raw or "").strip()
    name = re.sub(
        r"\(\s*source\s*:[^)]*\)",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    name = re.sub(r"[.?!,;:]+$", "", name).strip()
    name = re.sub(
        r"^(the\s+)?(owasp\s+)?",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    name = re.sub(r"\s+please$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"[.?!,;:]+$", "", name).strip()
    name = re.sub(
        r"\s+project$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    # "JuiceShop (no space)" → JuiceShop
    name = re.sub(r"\s*\(no space\)\s*", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s+board members?$", "", name, flags=re.IGNORECASE).strip()
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
