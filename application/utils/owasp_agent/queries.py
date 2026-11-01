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
        self, topic: Optional[str] = None, level: Optional[str] = None
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
        return QueryResult(
            ok=True,
            kind="board_person",
            data={
                "name": name,
                "member_years": years_m,
                "candidate_years": years_c,
                "roles": roles,
            },
            message=_format_person(name, years_m, years_c, roles),
            citations=[
                "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml"
            ],
        )

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
        if not keys:
            # Unknown topic taxonomy → fail closed / ambiguous
            return [], True
        matched: List[Dict[str, Any]] = []
        for item in items:
            tags = [str(t).lower() for t in (item.get("tags") or [])]
            topics = [str(t).lower() for t in (item.get("topics") or [])]
            name = str(item.get("name") or "").lower()
            desc = str(item.get("description") or "").lower()
            blob = f"{name} {desc}"
            if _topic_matches(keys, blob=blob, tokens=tags + topics):
                matched.append(item)
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
    return t.replace(" ", "_")


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
