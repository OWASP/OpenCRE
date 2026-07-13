"""Helpers for the ``embeddings.embedding_vec`` pgvector column.

Do **not** re-embed the full corpus on Heroku/production dynos — likely
OOM-killed. Re-embedding (fix missing / wrong-dim rows via the LLM) must run
only where there is enough RAM (local or a high-resource worker), then
sync/backfill vectors. Alembic on prod only: enable extension, add column,
copy CSV→vector for matching dims.

HNSW/IVFFlat indexes are deferred (Essential-1 capacity); see migration
``c7d8e9f0a1b2`` docstring for the follow-up plan.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional, Sequence, Set, Tuple

from sqlalchemy import text

HEROKU_REEMBED_WARNING = (
    "Do not re-embed the full corpus on Heroku/production dynos — likely "
    "OOM-killed. Re-embedding must run only on a machine with enough RAM, "
    "then sync/backfill vectors. Alembic on prod only copies CSV→vector."
)


class MultiDimEmbeddingError(RuntimeError):
    """Raised when more than one embedding dimension is present in the DB."""


def to_pgvector_literal(vector: Sequence[float]) -> str:
    """Render a vector in pgvector's text input format: ``[1.0,2.0,3.0]``."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def csv_embeddings_to_literal(csv: str) -> str:
    """Wrap a comma-separated CSV embedding string as a pgvector literal."""
    return f"[{(csv or '').strip()}]"


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
    rows = connection.execute(
        text("SELECT embedding_dim, embeddings FROM embeddings")
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
    if getattr(getattr(connection, "dialect", None), "name", None) != "postgresql":
        # SQLite / others: probe via PRAGMA or SQLAlchemy inspector if needed.
        dialect_name = getattr(getattr(connection, "dialect", None), "name", "")
        if dialect_name == "sqlite":
            rows = connection.execute(text("PRAGMA table_info(embeddings)")).fetchall()
            return any(r[1] == "embedding_vec" for r in rows)
        return False
    row = connection.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'embeddings' AND column_name = 'embedding_vec' "
            "LIMIT 1"
        )
    ).fetchone()
    return row is not None


def backfill_embedding_vec(connection: Any, dim: int) -> int:
    """Idempotent CSV → ``embedding_vec`` copy for rows matching ``dim``.

    Returns the number of rows reported updated (driver-dependent).
    """
    result = connection.execute(
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
