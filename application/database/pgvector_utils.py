"""Helpers for the ``embeddings.embedding_vec`` pgvector column.

Do **not** re-embed the full corpus on Heroku/production dynos — likely
OOM-killed. Re-embedding (fix missing / wrong-dim rows via the LLM) must run
only where there is enough RAM (local or a high-resource worker), then
sync/backfill vectors. Alembic on prod: enable extension, add column, copy
CSV→vector for matching dims, then DROP the legacy CSV ``embeddings`` column.

HNSW/IVFFlat indexes are deferred (Essential-1 capacity); see migration
``c7d8e9f0a1b2`` docstring for the follow-up plan.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional, Sequence, Set, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

HEROKU_REEMBED_WARNING = (
    "Do not re-embed the full corpus on Heroku/production dynos — likely "
    "OOM-killed. Re-embedding must run only on a machine with enough RAM, "
    "then sync/backfill vectors. Alembic on prod only copies CSV→vector "
    "then drops the CSV column."
)

PGVECTOR_UNAVAILABLE_EXIT_MSG = (
    "pgvector embeddings are required but unavailable on this database. "
    "Need Postgres with embeddings.embedding_vec (Alembic c7d8e9f0a1b2). "
    "SQLite cannot serve pgvector similarity (``<=>``). For Module C / "
    "Librarian on SQLite or CI, set CRE_LIBRARIAN_RETRIEVER_BACKEND=in_memory "
    "(reads ``embedding_vec`` Text literals into an in-RAM hub). For "
    "Postgres-side similarity, use local Postgres (make docker-postgres) or "
    "a remote Postgres URL with the vector extension."
)

EMBEDDING_VEC_REQUIRED_EXIT_MSG = (
    "embeddings.embedding_vec is required; the legacy CSV ``embeddings`` "
    "column is no longer a supported store. Postgres: run Alembic upgrade "
    "to c7d8e9f0a1b2. SQLite caches: rewrite with "
    "`python scripts/rewrite_sqlite_embeddings_to_vec.py --db PATH` or "
    "re-export from Postgres after the migration."
)


class MultiDimEmbeddingError(RuntimeError):
    """Raised when more than one embedding dimension is present in the DB."""


class PgVectorUnavailableError(RuntimeError):
    """Raised when a pgvector operation is requested without Postgres+vector."""


def _exit_with_message(msg: str) -> None:
    import logging

    logging.getLogger(__name__).error(msg)
    raise SystemExit(msg)


def fail_pgvector_unavailable(*, context: str = "") -> None:
    """Log and exit — callers must not silently fall back to CSV/sklearn.

    Intentionally raises ``SystemExit`` so CLI/import paths stop with a clear
    message when ``CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector`` (or other
    pgvector-only code) runs against SQLite / pre-migration Postgres.
    """
    detail = f" ({context})" if context else ""
    _exit_with_message(PGVECTOR_UNAVAILABLE_EXIT_MSG + detail)


def fail_embedding_vec_required(*, context: str = "") -> None:
    """Exit when the vector store column is missing (legacy CSV-only schema)."""
    detail = f" ({context})" if context else ""
    _exit_with_message(EMBEDDING_VEC_REQUIRED_EXIT_MSG + detail)


def connection_dialect_name(connection: Any) -> str:
    """Best-effort dialect name from a SQLAlchemy Connection/Engine/Session bind."""
    dialect = getattr(connection, "dialect", None)
    if dialect is not None:
        return getattr(dialect, "name", "") or ""
    bind = getattr(connection, "get_bind", None)
    if callable(bind):
        return connection_dialect_name(bind())
    engine = getattr(connection, "engine", None)
    if engine is not None:
        return connection_dialect_name(engine)
    return ""


def require_pgvector_connection(connection: Any, *, context: str = "") -> None:
    """Refuse SQLite (and unknown non-Postgres) when loading pgvector embeddings."""
    dialect = connection_dialect_name(connection)
    if dialect == "sqlite":
        fail_pgvector_unavailable(context=context or "sqlite connection")
    # Hermetic test fakes often omit dialect — allow those through.
    if dialect and dialect != "postgresql":
        fail_pgvector_unavailable(context=context or f"unsupported dialect {dialect!r}")


def _embeddings_table_columns(connection: Any) -> Optional[Set[str]]:
    """Return column names for ``embeddings``, or None when the table is absent."""
    dialect = connection_dialect_name(connection)
    if dialect == "sqlite":
        rows = _execute(connection, text("PRAGMA table_info(embeddings)")).fetchall()
        if not rows:
            return None
        return {str(r[1]) for r in rows}
    if dialect != "postgresql":
        return None
    rows = _execute(
        connection,
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'embeddings'"
        ),
    ).fetchall()
    if not rows:
        return None
    return {str(r[0]) for r in rows}


def require_embedding_vec_store(connection: Any, *, context: str = "") -> None:
    """Refuse legacy CSV-only schemas; require ``embedding_vec``.

    No-ops for hermetic fakes (empty dialect) and when the ``embeddings``
    table does not exist yet (caller will hit a normal SQLAlchemy error).
    """
    dialect = connection_dialect_name(connection)
    if not dialect:
        return
    cols = _embeddings_table_columns(connection)
    if cols is None:
        return
    if "embedding_vec" not in cols:
        fail_embedding_vec_required(context=context or f"{dialect} embeddings schema")


def _execute(connection: Any, statement: Any, params: Optional[dict] = None):
    """Run ``statement`` on a Connection/Session, or open one from an Engine.

    SQLAlchemy 2 removed ``Engine.execute``; Alembic upgrade passes a
    Connection, while runtime code often has ``session.get_bind()`` → Engine.
    """
    if isinstance(connection, Engine):
        with connection.connect() as conn:
            result = conn.execute(statement, params or {})
            conn.commit()
            return result
    return connection.execute(statement, params or {})


def to_pgvector_literal(vector: Sequence[float]) -> str:
    """Render a vector in pgvector's text input format: ``[1.0,2.0,3.0]``."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def csv_embeddings_to_literal(csv: str) -> str:
    """Wrap a comma-separated CSV embedding string as a pgvector literal."""
    return f"[{(csv or '').strip()}]"


def parse_stored_embedding_vec(value: Any) -> list[float]:
    """Parse a stored ``embedding_vec`` (pgvector / Text literal) to floats.

    Accepts ``[1.0, 2.0]``, ``1.0,2.0``, or a sequence of numbers.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [float(part.strip()) for part in s.split(",") if part.strip() != ""]


def parse_csv_embedding_dim(csv: str) -> int:
    """Return the number of floats implied by a CSV embeddings string."""
    parts = [p for p in (csv or "").split(",") if p.strip() != ""]
    return len(parts)


def collect_distinct_dims(
    rows: Iterable[Tuple[Optional[int], Optional[str]]],
) -> Set[int]:
    """Collect distinct dims from ``(embedding_dim, embeddings_csv)`` rows."""
    dims: Set[int] = set()
    for embedding_dim, csv in rows:
        if embedding_dim is not None:
            dims.add(int(embedding_dim))
            continue
        if csv is None or str(csv).strip() == "":
            continue
        dims.add(parse_csv_embedding_dim(str(csv)))
    return dims


def require_single_embedding_dim(connection: Any) -> int:
    """Return the single project-wide embedding dim or raise.

    Prefers ``embedding_dim`` metadata; falls back to CSV length. If the table
    is empty, uses ``CRE_EMBED_EXPECTED_DIM`` when set.
    """
    rows = _execute(
        connection, text("SELECT embedding_dim, embeddings FROM embeddings")
    ).fetchall()
    dims = collect_distinct_dims((row[0], row[1]) for row in rows)
    if len(dims) > 1:
        raise MultiDimEmbeddingError(
            f"multiple embedding dimensions detected in DB: {sorted(dims)}. "
            "Refuse to add embedding_vec — reconcile dims offline (do not "
            "re-embed on Heroku). " + HEROKU_REEMBED_WARNING
        )
    if len(dims) == 1:
        return next(iter(dims))

    env_dim = (os.environ.get("CRE_EMBED_EXPECTED_DIM", "") or "").strip()
    if env_dim:
        return int(env_dim)
    raise RuntimeError(
        "embeddings table has no vectors to infer dimension; set "
        "CRE_EMBED_EXPECTED_DIM before running this migration. "
        + HEROKU_REEMBED_WARNING
    )


def embedding_vec_column_exists(connection: Any) -> bool:
    """True when ``embeddings.embedding_vec`` exists (Postgres information_schema)."""
    dialect_name = getattr(getattr(connection, "dialect", None), "name", "") or ""

    if dialect_name == "sqlite":
        rows = _execute(connection, text("PRAGMA table_info(embeddings)")).fetchall()
        return any(r[1] == "embedding_vec" for r in rows)
    if dialect_name != "postgresql":
        return False
    row = _execute(
        connection,
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'embeddings' AND column_name = 'embedding_vec' "
            "LIMIT 1"
        ),
    ).fetchone()
    return row is not None


def backfill_embedding_vec(connection: Any, dim: int) -> int:
    """Idempotent CSV → ``embedding_vec`` copy for rows matching ``dim``.

    Returns the number of rows reported updated (driver-dependent).
    """
    result = _execute(
        connection,
        text(
            """
            UPDATE embeddings
            SET embedding_vec = CAST(('[' || embeddings || ']') AS vector)
            WHERE embedding_vec IS NULL
              AND embeddings IS NOT NULL
              AND btrim(embeddings) <> ''
              AND (
                    embedding_dim = :dim
                 OR (
                        embedding_dim IS NULL
                    AND (
                          length(embeddings)
                          - length(replace(embeddings, ',', ''))
                          + 1
                        ) = :dim
                 )
              )
            """
        ),
        {"dim": dim},
    )
    return int(getattr(result, "rowcount", 0) or 0)


def most_similar_id_sql(id_column: str) -> str:
    """SQL for top-1 cosine similarity over ``embedding_vec``.

    ``id_column`` must be ``cre_id`` or ``node_id`` (caller-validated).
    Score is ``1 - (embedding_vec <=> query)`` (cosine similarity).
    """
    if id_column not in ("cre_id", "node_id"):
        raise ValueError(f"id_column must be cre_id or node_id, got {id_column!r}")
    return (
        f"SELECT {id_column} AS object_id, "
        f"1 - (embedding_vec <=> CAST(:q AS vector)) AS score "
        f"FROM embeddings "
        f"WHERE doc_type = :doc_type AND {id_column} IS NOT NULL "
        f"AND embedding_vec IS NOT NULL "
        f"ORDER BY embedding_vec <=> CAST(:q AS vector) "
        f"LIMIT 1"
    )
