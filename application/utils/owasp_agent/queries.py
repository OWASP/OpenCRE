"""Fail-closed structured query tools over the local OWASP meta index."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from application.utils.owasp_agent.geocode import (
    GeocodeError,
    geocode_place,
    nearest_by_coords,
)
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import QueryResult

# Topic keyword sets — require explicit evidence in tags/description/name.
TOPIC_KEYWORDS: Dict[str, Sequence[str]] = {
    "ai_security": (
        "ai",  # exact tag / word-boundary only (see _topic_matches)
        "ai security",
        "artificial intelligence",
        "machine learning",
        "llm",
        "ml security",
        "genai",
        "llm security",
    ),
    "appsec": (
        "appsec",
        "application security",
        "web security",
        "software security",
        "asvs",
        "wstg",
    ),
    "cryptography": (
        "cryptography",
        "crypto",
        "encryption",
        "cryptographic",
        "tls",
        "openssl",
    ),
    "supply_chain": (
        "supply chain",
        "supply-chain",
        "dependency",
        "sbom",
        "software supply",
    ),
}


class MetaQueries:
    def __init__(
        self,
        store: IndexStore,
        geocode_fn=geocode_place,
    ) -> None:
        self.store = store
        self.geocode_fn = geocode_fn

    def count_chapters(self) -> QueryResult:
        items = self._safe_entities("chapter")
        if items is None:
            return items  # type: ignore[return-value]
        if not items:
            return QueryResult(
                ok=False,
                kind="count_chapters",
                message=(
                    "No chapters are indexed yet. Run `make owasp-agent-sync` "
                    "(with Nest and/or GitHub sources) before I can answer counts."
                ),
            )
        clean = [i for i in items if not i.get("_conflict")]
        conflicted = [i for i in items if i.get("_conflict")]
        if conflicted and not clean:
            return QueryResult(
                ok=False,
                kind="count_chapters",
                message=(
                    "Chapter Nest vs GitHub metadata conflicts on every indexed "
                    "chapter (fail closed). Reconcile sources or re-sync."
                ),
                clarify="Should I ignore GitHub or Nest for chapter counts?",
            )
        return QueryResult(
            ok=True,
            kind="count_chapters",
            data={"count": len(clean), "conflicted": len(conflicted)},
            message=f"There are {len(clean)} OWASP chapters in the local index."
            + (f" ({len(conflicted)} conflicted rows excluded.)" if conflicted else ""),
            citations=_citations(clean[:5]),
        )

    def count_projects(
        self,
        topic: Optional[str] = None,
        level: Optional[str] = None,
        list_mode: bool = False,
    ) -> QueryResult:
        items = self._safe_entities("project")
        if not isinstance(items, list):
            return items  # type: ignore[return-value]
        if not items:
            return QueryResult(
                ok=False,
                kind="count_projects",
                message=(
                    "No projects are indexed yet. Run `make owasp-agent-sync` "
                    "before I can answer project counts."
                ),
            )
        filtered = [p for p in items if not p.get("_conflict")]
        conflicted_n = len(items) - len(filtered)
        if level:
            filtered = [
                p
                for p in filtered
                if str(p.get("level") or "").lower() == level.lower()
            ]
        if topic:
            matched, ambiguous = self._filter_by_topic(filtered, topic)
            if ambiguous:
                return QueryResult(
                    ok=False,
                    kind="count_projects",
                    message=(
                        f"I cannot confidently filter projects for topic {topic!r} "
                        "from Nest/GitHub tags and keywords. "
                        "Please define the filter more narrowly (e.g. exact tag)."
                    ),
                    clarify="Which tags or keywords should count as this topic?",
                )
            filtered = matched
        if list_mode:
            rows = sorted(filtered, key=lambda p: str(p.get("name") or "").lower())
            lines = [
                f"| {p.get('name') or p.get('key')} | {p.get('level') or 'n/a'} | {p.get('url') or 'n/a'} |"
                for p in rows[:40]
            ]
            more = f" ({len(rows) - 40} more not shown.)" if len(rows) > 40 else ""
            # Lowercase "| project |" so synth/demo detectors match case-sensitively.
            table = "| project | level | url |\n|---|---|---|\n" + (
                "\n".join(lines) if lines else "| (none) | n/a | n/a |"
            )
            return QueryResult(
                ok=True,
                kind="list_projects",
                data={
                    "count": len(filtered),
                    "topic": topic,
                    "level": level,
                    "projects": [_public_entity(p) for p in rows[:40]],
                    "conflicted_excluded": conflicted_n,
                },
                message=(
                    f"Found {len(filtered)} OWASP projects"
                    + (f" matching topic {topic!r}" if topic else "")
                    + (f" at level {level!r}" if level else "")
                    + f".{more}\n\n{table}"
                ),
                citations=_citations(rows[:10]),
            )
        return QueryResult(
            ok=True,
            kind="count_projects",
            data={
                "count": len(filtered),
                "topic": topic,
                "level": level,
                "conflicted_excluded": conflicted_n,
            },
            message=f"Found {len(filtered)} OWASP projects"
            + (f" matching topic {topic!r}" if topic else "")
            + (f" at level {level!r}" if level else "")
            + ".",
            citations=_citations(filtered[:5]),
        )

    def board_members(self, year: int) -> QueryResult:
        rows = self.store.list_entities("board_member")
        members = [r for r in rows if int(r.get("year") or 0) == int(year)]
        if not members:
            return QueryResult(
                ok=False,
                kind="board_members",
                message=f"No board members found for year {year} in indexed GitHub board-history.",
            )
        names = sorted({str(m.get("name")) for m in members})
        return QueryResult(
            ok=True,
            kind="board_members",
            data={"year": year, "members": names},
            message=f"OWASP board members for {year}: " + ", ".join(names) + ".",
            citations=[
                "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
            ],
        )

    def board_person(self, name: str, year: Optional[int] = None) -> QueryResult:
        target = _norm(name)
        if not target:
            return QueryResult(
                ok=False,
                kind="board_person",
                clarify="Which board member or candidate name should I look up?",
                message="I need a person's name to look up board or candidate history.",
            )
        members = self.store.list_entities("board_member")
        candidates = self.store.list_entities("board_candidate")
        hit_m = [m for m in members if target in _norm(str(m.get("name") or ""))]
        hit_c = [c for c in candidates if target in _norm(str(c.get("name") or ""))]
        if year is not None:
            hit_m = [m for m in hit_m if int(m.get("year") or 0) == int(year)]
            hit_c = [c for c in hit_c if int(c.get("year") or 0) == int(year)]
        if not hit_m and not hit_c:
            return QueryResult(
                ok=False,
                kind="board_person",
                message=(
                    f"I found no board membership or candidacy for {name!r} "
                    "in indexed GitHub sources (fail closed)."
                ),
            )
        years_m = sorted({int(m["year"]) for m in hit_m})
        years_c = sorted({int(c["year"]) for c in hit_c})
        roles = sorted({f"{m.get('year')}:{m.get('role') or 'member'}" for m in hit_m})
        # Prefer earliest candidacy statement (first board interview / statement)
        statements = sorted(
            [
                c
                for c in hit_c
                if (c.get("statement") or "").strip() or (c.get("url") or "").strip()
            ],
            key=lambda c: int(c.get("year") or 0),
        )
        first = statements[0] if statements else None
        msg = _format_person(name, years_m, years_c, roles)
        if first:
            yr = first.get("year")
            url = first.get("url") or ""
            excerpt = (first.get("statement") or "").strip()
            msg += f" First indexed candidacy: {yr}."
            if url:
                msg += f" Candidate page: {url}."
            if excerpt:
                msg += f" Statement excerpt: {excerpt}"
        citations = [
            "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
        ]
        if first and first.get("url"):
            citations.append(str(first["url"]))
        return QueryResult(
            ok=True,
            kind="board_person",
            data={
                "name": name,
                "member_years": years_m,
                "candidate_years": years_c,
                "roles": roles,
                "first_candidacy": _public_entity(first) if first else None,
            },
            message=msg,
            citations=citations,
        )

    def board_members_years(self, years: Sequence[int]) -> QueryResult:
        cleaned = sorted({int(y) for y in years})
        if not cleaned:
            return QueryResult(
                ok=False,
                kind="board_members",
                message="Which board year should I look up?",
                clarify="Please provide a year (e.g. 2025).",
            )
        if len(cleaned) == 1:
            return self.board_members(cleaned[0])
        parts = []
        data = {}
        citations = [
            "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
        ]
        ok_any = False
        for year in cleaned:
            r = self.board_members(year)
            if r.ok:
                ok_any = True
                data[str(year)] = r.data
                parts.append(r.message.rstrip("."))
            else:
                parts.append(f"No board members found for year {year}")
        return QueryResult(
            ok=ok_any,
            kind="board_members",
            data=data,
            message=" ".join(p + "." for p in parts),
            citations=citations,
        )

    def chapter_lookup(
        self, place: Optional[str] = None, places: Optional[Sequence[str]] = None
    ) -> QueryResult:
        targets = [p for p in (places or []) if p and str(p).strip()]
        if place and place.strip():
            targets = [place.strip()] + [t for t in targets if t != place.strip()]
        if not targets:
            return QueryResult(
                ok=False,
                kind="chapter_lookup",
                message="Which chapter or city should I look up?",
                clarify="Please name a city or chapter (e.g. Athens, Los Angeles).",
            )
        chapters = self._merged_chapters()
        messages: List[str] = []
        rows: List[Dict[str, Any]] = []
        citations: List[str] = []
        found_any = False
        for target in targets:
            hit = _match_chapter(chapters, target)
            alias = _metro_chapter_alias(target) if not hit else None
            via_alias = False
            if not hit and alias:
                hit = _match_chapter(chapters, alias)
                via_alias = bool(hit)
            if not hit:
                messages.append(
                    f"No OWASP chapter is indexed for {target!r} "
                    "(no active chapter and no historical chapter page in the local index)."
                )
                rows.append({"query": target, "found": False})
                continue
            found_any = True
            leaders = [x for x in (hit.get("leaders") or []) if x]
            active = hit.get("active")
            name = hit.get("name") or hit.get("key")
            url = hit.get("url") or ""
            suburb_bit = (
                f" For {target}, the nearest indexed chapter is {name}."
                if via_alias
                else ""
            )
            if active is False:
                leader_bit = (
                    f" Last known leaders: {', '.join(leaders)}."
                    if leaders
                    else " No leaders are indexed."
                )
                messages.append(
                    f"There is no active OWASP chapter for {name}. "
                    f"A chapter page is indexed but marked inactive "
                    f"(site data: Needs Website Update / no pages).{leader_bit}"
                    + suburb_bit
                    + (f" Page: {url}." if url else "")
                )
            else:
                leader_bit = (
                    f" Leaders: {', '.join(leaders)}."
                    if leaders
                    else " Leaders are not indexed for this chapter."
                )
                status = "active" if active is True else "indexed"
                messages.append(
                    f"OWASP chapter {name} is {status}.{leader_bit}"
                    + suburb_bit
                    + (f" Page: {url}." if url else "")
                )
            if url:
                citations.append(str(url))
            rows.append(
                {
                    "query": target,
                    "found": True,
                    "chapter": _public_entity(hit),
                    "leaders": leaders,
                    "active": active,
                    "via_suburb_alias": via_alias,
                }
            )
        return QueryResult(
            ok=found_any,
            kind="chapter_lookup",
            data={"results": rows},
            message=" ".join(messages),
            citations=citations,
        )

    def membership_info(
        self,
        country: Optional[str] = None,
        countries: Optional[Sequence[str]] = None,
        student: bool = False,
        renew_only: bool = False,
    ) -> QueryResult:
        from application.utils.owasp_agent.membership import format_membership_answer

        discount_map: Dict[str, bool] = {}
        for row in self.store.list_entities("membership_country"):
            name = str(row.get("name") or "")
            if name:
                from application.utils.owasp_agent.membership import normalize_country

                discount_map[normalize_country(name)] = bool(row.get("discount"))
        payload = format_membership_answer(
            country=country,
            compare_countries=countries,
            student=student,
            renew_only=renew_only,
            country_discount_map=discount_map or None,
        )
        return QueryResult(
            ok=bool(payload.get("ok")),
            kind="membership",
            data=payload.get("data"),
            message=str(payload.get("message") or ""),
            citations=list(payload.get("citations") or []),
        )

    def talk_lookup(
        self, person: Optional[str] = None, topic: Optional[str] = None
    ) -> QueryResult:
        """Fail-closed: only answer from indexed event talks (never invent)."""
        events = self._safe_entities("event")
        if not isinstance(events, list):
            events = []
        person_n = _norm(person or "")
        topic_n = (topic or "").lower().strip()
        # Topic-only matches on event titles (e.g. "AppSec Days") are too loose for
        # "Quote <person>'s keynote" — require the person when one was asked.
        hits: List[Dict[str, Any]] = []
        for ev in events:
            if ev.get("_conflict"):
                continue
            talks = [str(t) for t in (ev.get("talks") or [])]
            blob = " ".join(
                talks + [str(ev.get("name") or ""), str(ev.get("description") or "")]
            ).lower()
            if person_n:
                if person_n not in blob and person_n not in _norm(
                    str(ev.get("name") or "")
                ):
                    continue
                if topic_n and topic_n not in blob and not talks:
                    # Person hit without topic evidence still counts (rare speaker index).
                    pass
                hits.append(ev)
                continue
            if topic_n and topic_n in blob:
                hits.append(ev)
        if not hits:
            who = person or "that person"
            about = f" about {topic}" if topic else ""
            return QueryResult(
                ok=True,
                kind="talk_lookup",
                data={"person": person, "topic": topic, "events": []},
                message=(
                    f"I have no indexed OWASP talk or keynote by {who}{about}. "
                    "I will not invent talk content (fail closed). "
                    "If this was a board candidate interview/statement, ask about their "
                    "board candidacy instead."
                ),
            )
        top = hits[0]
        return QueryResult(
            ok=True,
            kind="talk_lookup",
            data={"events": [_public_entity(e) for e in hits[:5]]},
            message=(
                f"Indexed match: {top.get('name')} on {top.get('start_date')}. "
                f"Talks: {'; '.join(top.get('talks') or []) or 'n/a'}."
            ),
            citations=_citations(hits[:3]),
        )

    def _merged_chapters(self) -> List[Dict[str, Any]]:
        """Merge chapter fields across nest/site/github for leaders/active."""
        by_key: Dict[str, Dict[str, Any]] = {}
        for item in self.store.list_entities("chapter"):
            key = str(item.get("key") or "")
            if not key:
                continue
            cur = by_key.get(key)
            if cur is None:
                by_key[key] = dict(item)
                continue
            # Prefer non-empty leaders / explicit active / url
            if item.get("leaders") and not cur.get("leaders"):
                cur["leaders"] = item.get("leaders")
            elif item.get("leaders") and cur.get("leaders"):
                merged = list(cur.get("leaders") or [])
                for n in item.get("leaders") or []:
                    if n not in merged:
                        merged.append(n)
                cur["leaders"] = merged
            if cur.get("active") is None and item.get("active") is not None:
                cur["active"] = item.get("active")
            if item.get("active") is False:
                cur["active"] = False
            if item.get("url") and not cur.get("url"):
                cur["url"] = item.get("url")
            if item.get("country") and not cur.get("country"):
                cur["country"] = item.get("country")
            if item.get("name") and (
                not cur.get("name") or cur.get("source") != "site"
            ):
                if item.get("source") == "site" or not cur.get("name"):
                    cur["name"] = item.get("name")
        return list(by_key.values())

    def board_candidate_stats(self, names: Sequence[str]) -> QueryResult:
        cleaned = [n.strip() for n in names if n and n.strip()]
        if not cleaned:
            return QueryResult(
                ok=False,
                kind="board_candidate_stats",
                clarify="Which candidate names should I count?",
                message="I need one or more names to count board candidacies.",
            )
        candidates = self.store.list_entities("board_candidate")
        # Also count member years as presence in board history if no candidates table.
        members = self.store.list_entities("board_member")
        stats: Dict[str, Dict[str, Any]] = {}
        for name in cleaned:
            target = _norm(name)
            c_years = sorted(
                {
                    int(c["year"])
                    for c in candidates
                    if target in _norm(str(c.get("name") or ""))
                }
            )
            m_years = sorted(
                {
                    int(m["year"])
                    for m in members
                    if target in _norm(str(m.get("name") or ""))
                }
            )
            # Prefer explicit candidates; if none, report member appearances fail-closed note.
            stats[name] = {
                "candidate_years": c_years,
                "candidate_count": len(c_years),
                "member_years": m_years,
                "member_count": len(m_years),
            }
        lines = []
        for name, s in stats.items():
            if s["candidate_count"]:
                lines.append(
                    f"{name}: appeared as candidate {s['candidate_count']} time(s) "
                    f"({', '.join(map(str, s['candidate_years']))})"
                )
            elif s["member_count"]:
                lines.append(
                    f"{name}: no candidate rows indexed; board membership years "
                    f"{', '.join(map(str, s['member_years']))} "
                    "(from board-history members only)."
                )
            else:
                lines.append(f"{name}: no indexed candidate or board records.")
        return QueryResult(
            ok=True,
            kind="board_candidate_stats",
            data=stats,
            message=" ".join(lines),
            citations=[
                "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
            ],
        )

    def events_near(
        self,
        place: Optional[str],
        topic: Optional[str] = None,
        upcoming_only: bool = True,
        include_past: bool = False,
        now: Optional[datetime] = None,
    ) -> QueryResult:
        if not place or not place.strip():
            return QueryResult(
                ok=False,
                kind="events_near",
                clarify="Which city or place are you in?",
                message="I don't know where you are. Please tell me which city you are in.",
            )
        try:
            origin = self.geocode_fn(place.strip())
        except GeocodeError as exc:
            return QueryResult(
                ok=False,
                kind="events_near",
                message=f"I could not geocode {place!r} ({exc}). Please try another place name.",
                clarify="Which city should I use?",
            )

        events = self._safe_entities("event")
        if not isinstance(events, list):
            # Fall back to chapters when events missing.
            chapters = [
                c
                for c in (self._safe_entities("chapter") or [])
                if isinstance(c, dict) and not c.get("_conflict")
            ]
            if not chapters:
                return QueryResult(
                    ok=False,
                    kind="events_near",
                    message="No events or chapters with coordinates are indexed yet.",
                )
            nearest_ch = nearest_by_coords(origin, chapters, limit=3)
            if not nearest_ch:
                return QueryResult(
                    ok=False,
                    kind="events_near",
                    message="No chapters with coordinates near that place are indexed.",
                )
            top = nearest_ch[0]
            return QueryResult(
                ok=True,
                kind="events_near",
                data={
                    "place": place,
                    "nearest_chapter": _public_entity(top),
                    "events": [],
                },
                message=(
                    f"You told me you are in {place}. The nearest indexed OWASP chapter is "
                    f"{top.get('name')} (~{top.get('distance_km')} km). "
                    "I do not have upcoming meetup details indexed yet (fail closed on talks)."
                ),
                citations=_citations([top]),
            )

        now = now or datetime.now(timezone.utc)
        filtered: List[Dict[str, Any]] = []
        for ev in events:
            if ev.get("_conflict"):
                continue  # fail closed on conflicting Nest/GitHub event fields
            start = _parse_dt(ev.get("start_date") or "")
            if upcoming_only and not include_past:
                if start is None:
                    continue  # fail closed: unknown date
                if start < now:
                    continue
            elif include_past and not upcoming_only:
                pass
            elif include_past and upcoming_only:
                # both allowed — no date filter
                pass
            if topic:
                matched, ambiguous = self._filter_by_topic([ev], topic)
                if ambiguous or not matched:
                    continue
            filtered.append(ev)

        nearest = nearest_by_coords(origin, filtered, limit=5)
        if not nearest:
            # Try chapters for geography, still fail closed on talks/conflicts.
            chapters = [
                c
                for c in self.store.prefer_source_entities("chapter")
                if not c.get("_conflict")
            ]
            # Prefer chapters with coords; for a short metro alias list, map place→chapter.
            alias = _metro_chapter_alias(place)
            if alias:
                for ch in chapters:
                    key = str(ch.get("key") or "").lower()
                    name = str(ch.get("name") or "").lower()
                    if alias in key or alias in name:
                        return QueryResult(
                            ok=True,
                            kind="events_near",
                            data={
                                "place": place,
                                "nearest_chapter": _public_entity(ch),
                                "events": [],
                            },
                            message=(
                                f"You told me you are in {place}. Nearest indexed OWASP chapter is "
                                f"{ch.get('name')}. No matching upcoming events indexed"
                                + (f" for topic {topic!r}." if topic else ".")
                            ),
                            citations=_citations([ch]),
                        )
            nearest_ch = nearest_by_coords(origin, chapters, limit=1)
            if nearest_ch:
                ch = nearest_ch[0]
                return QueryResult(
                    ok=True,
                    kind="events_near",
                    data={
                        "place": place,
                        "nearest_chapter": _public_entity(ch),
                        "events": [],
                    },
                    message=(
                        f"You told me you are in {place}. Nearest chapter: {ch.get('name')} "
                        f"(~{ch.get('distance_km')} km). No matching upcoming events indexed"
                        + (f" for topic {topic!r}." if topic else ".")
                    ),
                    citations=_citations([ch]),
                )
            return QueryResult(
                ok=False,
                kind="events_near",
                message="No nearby events found in the index for that place/topic.",
            )

        top = nearest[0]
        talks = top.get("talks") or []
        talk_bit = (
            " Talks: " + "; ".join(talks) + "."
            if talks
            else " Talk details are not indexed (fail closed)."
        )
        return QueryResult(
            ok=True,
            kind="events_near",
            data={
                "place": place,
                "events": [_public_entity(e) for e in nearest],
            },
            message=(
                f"You told me you are in {place}. The nearest matching OWASP event is "
                f"{top.get('name')} on {top.get('start_date')} "
                f"(~{top.get('distance_km')} km)."
                f"{talk_bit} Link: {top.get('url') or 'n/a'}."
            ),
            citations=_citations(nearest[:3]),
        )

    def _safe_entities(self, kind: str) -> Any:
        items = self.store.prefer_source_entities(kind)
        # Entities with conflicts are still listed but marked; callers may skip.
        return items

    def _filter_by_topic(
        self, items: List[Dict[str, Any]], topic: str
    ) -> Tuple[List[Dict[str, Any]], bool]:
        keys = TOPIC_KEYWORDS.get(_topic_key(topic))
        free_text = False
        if not keys:
            # Free-text topic: substring/token match on name/desc/tags (not invent).
            raw = (topic or "").strip().lower()
            if not raw or len(raw) < 2:
                return [], True
            free_text = True
            keys = tuple(
                part for part in re.split(r"[\s/_-]+", raw) if len(part) >= 2
            ) or (raw,)
        matched: List[Dict[str, Any]] = []
        for item in items:
            tags = [str(t).lower() for t in (item.get("tags") or [])]
            topics = [str(t).lower() for t in (item.get("topics") or [])]
            name = str(item.get("name") or "").lower()
            desc = str(item.get("description") or "").lower()
            blob = f"{name} {desc}"
            if _topic_matches(keys, blob=blob, tokens=tags + topics):
                matched.append(item)
        # Unknown free-text with zero evidence → ambiguous (fail closed).
        if free_text and not matched:
            return [], True
        return matched, False


def _topic_matches(keys: Sequence[str], blob: str, tokens: Sequence[str]) -> bool:
    token_set = {t.strip() for t in tokens if t and t.strip()}
    for key in keys:
        k = key.lower()
        if k in token_set:
            return True
        # Short tokens (e.g. "llm") require word boundaries in free text.
        if len(k) <= 3:
            if re.search(rf"\b{re.escape(k)}\b", blob):
                return True
        elif k in blob:
            return True
    return False


def _topic_key(topic: str) -> str:
    t = (topic or "").strip().lower()
    if t in TOPIC_KEYWORDS:
        return t
    if "ai" in t:
        return "ai_security"
    if "appsec" in t or "application security" in t:
        return "appsec"
    if "crypto" in t or "encrypt" in t:
        return "cryptography"
    if "supply" in t and "chain" in t:
        return "supply_chain"
    return t.replace(" ", "_").replace("-", "_")


def _citations(items: Sequence[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for item in items:
        url = item.get("url")
        if url:
            out.append(str(url))
    return out


_PUBLIC_FIELDS = (
    "key",
    "name",
    "url",
    "city",
    "country",
    "region",
    "latitude",
    "longitude",
    "distance_km",
    "start_date",
    "end_date",
    "talks",
    "topics",
    "tags",
    "level",
    "chapter_key",
    "source",
    "leaders",
    "active",
    "meetings",
    "year",
    "statement",
    "notes",
)


def _public_entity(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip raw Nest/GitHub payloads before returning to chat clients."""
    return {k: item.get(k) for k in _PUBLIC_FIELDS if k in item}


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def _parse_dt(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    # Try common ISO forms
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            dt = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Last resort: leading YYYY-MM-DD
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


def _format_person(
    name: str, years_m: List[int], years_c: List[int], roles: List[str]
) -> str:
    parts = [f"For {name}:"]
    if years_m:
        parts.append(f"board member in {', '.join(map(str, years_m))}")
        if roles:
            parts.append(f"(roles: {', '.join(roles)})")
    if years_c:
        parts.append(f"candidate in {', '.join(map(str, years_c))}")
    return " ".join(parts) + "."


def _match_chapter(
    chapters: List[Dict[str, Any]], place: str
) -> Optional[Dict[str, Any]]:
    target = _norm(place)
    if not target:
        return None
    for prefix in ("owasp ", "chapter ", "the "):
        if target.startswith(prefix):
            target = target[len(prefix) :]
    best = None
    for ch in chapters:
        key = _norm(str(ch.get("key") or "").replace("-", " "))
        name = _norm(str(ch.get("name") or ""))
        city = _norm(str(ch.get("city") or ""))
        hay = f"{key} {name} {city}"
        if target == key or target == city or target in name or name.endswith(target):
            return ch
        if target.replace(" ", "") == key.replace(" ", ""):
            return ch
        if target in hay and best is None:
            best = ch
    return best


def _metro_chapter_alias(place: str) -> Optional[str]:
    """Map well-known localities to chapter key/name fragments without geocoding."""
    p = _norm(place)
    aliases = {
        "pasadena": "los angeles",
        "santa monica": "los angeles",
        "glendale": "los angeles",
        "burbank": "los angeles",
        "oakland": "los angeles",
        "beverly hills": "los angeles",
        "long beach": "los angeles",
        "croydon": "london",
        "peckham": "london",
        "potsdam": "berlin",
        "yokohama": "tokyo",
        "brooklyn": "new york",
        "manhattan": "new york",
        "cambridge": "boston",
    }
    return aliases.get(p)
