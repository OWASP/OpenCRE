"""SQLite-backed local OWASP metadata index (separate from CRE graph)."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence

from application.utils.owasp_agent.models import (
    BoardCandidate,
    BoardMember,
    Chapter,
    Concept,
    Event,
    Project,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_entity (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (kind, key, source)
);

CREATE TABLE IF NOT EXISTS owasp_concept (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    evidence_urls TEXT NOT NULL DEFAULT '[]',
    entity_keys TEXT NOT NULL DEFAULT '[]',
    merged_into TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'auto',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_merge_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_key TEXT NOT NULL,
    into_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def default_db_path() -> str:
    return os.environ.get(
        "OWASP_AGENT_DB",
        os.path.join(os.getcwd(), "tmp", "owasp_agent.sqlite"),
    )


class IndexStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or default_db_path()
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent and parent != os.path.abspath(self.db_path):
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def log_sync(self, source: str, status: str, detail: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sync_log(source, status, detail, created_at) VALUES (?,?,?,?)",
                (source, status, detail, _now()),
            )

    def upsert_entity(
        self, kind: str, key: str, name: str, source: str, payload: Dict[str, Any]
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_entity(kind, key, name, source, payload, fetched_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(kind, key, source) DO UPDATE SET
                    name=excluded.name,
                    payload=excluded.payload,
                    fetched_at=excluded.fetched_at
                """,
                (kind, key, name, source, json.dumps(payload), _now()),
            )

    def upsert_chapter(self, chapter: Chapter) -> None:
        self.upsert_entity(
            "chapter", chapter.key, chapter.name, chapter.source, chapter.to_dict()
        )

    def upsert_project(self, project: Project) -> None:
        self.upsert_entity(
            "project", project.key, project.name, project.source, project.to_dict()
        )

    def upsert_event(self, event: Event) -> None:
        self.upsert_entity(
            "event", event.key, event.name, event.source, event.to_dict()
        )

    def upsert_board_member(self, member: BoardMember) -> None:
        key = f"{member.year}:{_norm(member.name)}"
        self.upsert_entity(
            "board_member", key, member.name, member.source, member.to_dict()
        )

    def upsert_board_candidate(self, candidate: BoardCandidate) -> None:
        key = f"{candidate.year}:{_norm(candidate.name)}"
        self.upsert_entity(
            "board_candidate",
            key,
            candidate.name,
            candidate.source,
            candidate.to_dict(),
        )

    def list_entities(
        self, kind: str, source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if source:
                rows = conn.execute(
                    "SELECT payload, source FROM meta_entity WHERE kind=? AND source=?",
                    (kind, source),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload, source FROM meta_entity WHERE kind=?",
                    (kind,),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"])
            payload["_index_source"] = row["source"]
            out.append(payload)
        return out

    def prefer_source_entities(
        self, kind: str, preferred: Sequence[str] = ("nest", "site", "github")
    ) -> List[Dict[str, Any]]:
        """Deduplicate by key preferring Nest then site then GitHub; flag conflicts."""
        by_key: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for item in self.list_entities(kind):
            key = str(item.get("key") or "")
            src = str(item.get("source") or item.get("_index_source") or "")
            by_key.setdefault(key, {})[src] = item
        preferred_list = list(preferred)
        out: List[Dict[str, Any]] = []
        for key, sources in by_key.items():
            chosen = None
            for pref in preferred_list:
                if pref in sources:
                    chosen = sources[pref]
                    break
            if chosen is None:
                chosen = next(iter(sources.values()))
            conflicts = _critical_conflicts(sources)
            chosen = dict(chosen)
            chosen["_conflict"] = conflicts
            out.append(chosen)
        return out

    def upsert_concept(self, concept: Concept) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO owasp_concept(
                    key, name, category, description, evidence_urls, entity_keys,
                    merged_into, source, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    description=excluded.description,
                    evidence_urls=excluded.evidence_urls,
                    entity_keys=excluded.entity_keys,
                    merged_into=excluded.merged_into,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    concept.key,
                    concept.name,
                    concept.category,
                    concept.description,
                    json.dumps(concept.evidence_urls),
                    json.dumps(concept.entity_keys),
                    concept.merged_into,
                    concept.source,
                    _now(),
                ),
            )

    def list_concepts(self, include_merged: bool = False) -> List[Concept]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM owasp_concept").fetchall()
        out: List[Concept] = []
        for row in rows:
            if not include_merged and row["merged_into"]:
                continue
            out.append(
                Concept(
                    key=row["key"],
                    name=row["name"],
                    category=row["category"],
                    description=row["description"] or "",
                    evidence_urls=json.loads(row["evidence_urls"] or "[]"),
                    entity_keys=json.loads(row["entity_keys"] or "[]"),
                    merged_into=row["merged_into"] or "",
                    source=row["source"] or "auto",
                )
            )
        return out

    def mark_concept_merged(self, from_key: str, into_key: str, reason: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE owasp_concept SET merged_into=?, updated_at=? WHERE key=?",
                (into_key, _now(), from_key),
            )
            conn.execute(
                "INSERT INTO concept_merge_audit(from_key, into_key, reason, created_at) VALUES (?,?,?,?)",
                (from_key, into_key, reason, _now()),
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def _critical_conflicts(sources: Dict[str, Dict[str, Any]]) -> List[str]:
    """Compare Nest vs GitHub on a few critical fields."""
    if "nest" not in sources or "github" not in sources:
        return []
    nest, gh = sources["nest"], sources["github"]
    conflicts: List[str] = []
    for field in ("name", "country", "level", "latitude", "longitude"):
        a, b = nest.get(field), gh.get(field)
        if a in (None, "") or b in (None, ""):
            continue
        if isinstance(a, float) and isinstance(b, float):
            if abs(a - b) > 0.5:
                conflicts.append(field)
        elif str(a).strip().lower() != str(b).strip().lower():
            conflicts.append(field)
    return conflicts
