"""Local OWASP metadata index (tables alongside the CRE graph).

Backed by SQLAlchemy Core on the main app Postgres
(``DATABASE_URL`` / ``DEV_DATABASE_URL``). Tests may pass a SQLite path or set
``OWASP_AGENT_DB`` as an override.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from application.utils.postgres_url import is_postgres_url, sqlalchemy_postgres_url
from application.utils.owasp_agent.models import (
    BoardCandidate,
    BoardMember,
    Chapter,
    Concept,
    Event,
    Project,
)

_METADATA = sa.MetaData()

_meta_entity = sa.Table(
    "meta_entity",
    _METADATA,
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("key", sa.String, nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("source", sa.String, nullable=False),
    sa.Column("payload", sa.Text, nullable=False),
    sa.Column("fetched_at", sa.String, nullable=False),
    sa.PrimaryKeyConstraint("kind", "key", "source"),
)

_owasp_concept = sa.Table(
    "owasp_concept",
    _METADATA,
    sa.Column("key", sa.String, primary_key=True),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("description", sa.Text, nullable=False, server_default=""),
    sa.Column("evidence_urls", sa.Text, nullable=False, server_default="[]"),
    sa.Column("entity_keys", sa.Text, nullable=False, server_default="[]"),
    sa.Column("merged_into", sa.String, nullable=False, server_default=""),
    sa.Column("source", sa.String, nullable=False, server_default="auto"),
    sa.Column("updated_at", sa.String, nullable=False),
)

_sync_log = sa.Table(
    "sync_log",
    _METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source", sa.String, nullable=False),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("detail", sa.Text, nullable=False),
    sa.Column("created_at", sa.String, nullable=False),
)

_concept_merge_audit = sa.Table(
    "concept_merge_audit",
    _METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("from_key", sa.String, nullable=False),
    sa.Column("into_key", sa.String, nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("created_at", sa.String, nullable=False),
)


def app_db_url_and_key() -> tuple[Optional[str], Optional[str]]:
    """URL + env key Flask would use for this process (no sqlite fallback)."""
    flask_cfg = (
        (os.environ.get("FLASK_CONFIG") or os.environ.get("FLASK_ENV") or "development")
        .strip()
        .lower()
    )
    if flask_cfg in ("production", "prod"):
        keys = ("DATABASE_URL", "PROD_DATABASE_URL", "SQLALCHEMY_DATABASE_URI")
    else:
        keys = ("DEV_DATABASE_URL", "DATABASE_URL", "SQLALCHEMY_DATABASE_URI")
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw, key
    return None, None


def default_db_path() -> str:
    override = (os.environ.get("OWASP_AGENT_DB") or "").strip()
    if override:
        return override
    raw, _key = app_db_url_and_key()
    if raw:
        return raw
    raise RuntimeError(
        "OWASP agent index needs DATABASE_URL (or DEV_DATABASE_URL); "
        "no separate agent database"
    )


def _engine_url(target: str) -> str:
    if "://" in target:
        raw = target.strip()
        if is_postgres_url(raw):
            return sqlalchemy_postgres_url(raw)
        return raw
    return f"sqlite:///{os.path.abspath(target)}"


def _insert_for(engine: Engine, table: sa.Table) -> Any:
    if engine.dialect.name == "postgresql":
        return postgresql.insert(table)
    return sqlite.insert(table)


class IndexStore:
    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        engine: Optional[Engine] = None,
    ) -> None:
        """``db_path`` is a SQLAlchemy URL or a SQLite file path; ``engine`` wins."""
        self._owns_engine = engine is None
        if engine is not None:
            self.engine = engine
            self.db_path = str(engine.url)
        else:
            self.db_path = db_path or default_db_path()
            url = _engine_url(self.db_path)
            if url.startswith("sqlite"):
                parent = os.path.dirname(os.path.abspath(self.db_path))
                os.makedirs(parent, exist_ok=True)
                self.engine = sa.create_engine(url, poolclass=NullPool)
            else:
                self.engine = sa.create_engine(url, pool_pre_ping=True)
        self._init_schema()

    def _init_schema(self) -> None:
        _METADATA.create_all(self.engine, checkfirst=True)

    @contextmanager
    def _conn(self) -> Iterator[Connection]:
        with self.engine.begin() as conn:
            yield conn

    def log_sync(self, source: str, status: str, detail: str) -> None:
        with self._conn() as conn:
            conn.execute(
                sa.insert(_sync_log).values(
                    source=source, status=status, detail=detail, created_at=_now()
                )
            )

    def upsert_entity(
        self, kind: str, key: str, name: str, source: str, payload: Dict[str, Any]
    ) -> None:
        stmt = _insert_for(self.engine, _meta_entity).values(
            kind=kind,
            key=key,
            name=name,
            source=source,
            payload=json.dumps(payload),
            fetched_at=_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["kind", "key", "source"],
            set_={
                "name": stmt.excluded.name,
                "payload": stmt.excluded.payload,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        with self._conn() as conn:
            conn.execute(stmt)

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
        query = sa.select(
            _meta_entity.c.payload, _meta_entity.c.source  # type: ignore[arg-type]
        ).where(_meta_entity.c.kind == kind)
        if source:
            query = query.where(_meta_entity.c.source == source)
        with self._conn() as conn:
            rows = conn.execute(query).all()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row.payload)
            payload["_index_source"] = row.source
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
        stmt = _insert_for(self.engine, _owasp_concept).values(
            key=concept.key,
            name=concept.name,
            category=concept.category,
            description=concept.description,
            evidence_urls=json.dumps(concept.evidence_urls),
            entity_keys=json.dumps(concept.entity_keys),
            merged_into=concept.merged_into,
            source=concept.source,
            updated_at=_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={
                col: getattr(stmt.excluded, col)
                for col in (
                    "name",
                    "category",
                    "description",
                    "evidence_urls",
                    "entity_keys",
                    "merged_into",
                    "source",
                    "updated_at",
                )
            },
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def list_concepts(self, include_merged: bool = False) -> List[Concept]:
        with self._conn() as conn:
            rows = conn.execute(sa.select(_owasp_concept)).all()  # type: ignore[arg-type]
        out: List[Concept] = []
        for row in rows:
            if not include_merged and row.merged_into:
                continue
            out.append(
                Concept(
                    key=row.key,
                    name=row.name,
                    category=row.category,
                    description=row.description or "",
                    evidence_urls=json.loads(row.evidence_urls or "[]"),
                    entity_keys=json.loads(row.entity_keys or "[]"),
                    merged_into=row.merged_into or "",
                    source=row.source or "auto",
                )
            )
        return out

    def mark_concept_merged(self, from_key: str, into_key: str, reason: str) -> None:
        with self._conn() as conn:
            conn.execute(
                sa.update(_owasp_concept)
                .where(_owasp_concept.c.key == from_key)
                .values(merged_into=into_key, updated_at=_now())
            )
            conn.execute(
                sa.insert(_concept_merge_audit).values(
                    from_key=from_key,
                    into_key=into_key,
                    reason=reason,
                    created_at=_now(),
                )
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
