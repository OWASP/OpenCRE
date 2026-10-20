"""add half-precision HNSW index for the OWASP agent embeddings

Revision ID: e5f6a7b8c9d0
Revises: c9d0e1f2a3b4, f5a6b7c8d9e0
Create Date: 2026-10-20

Vector search over ``embeddings`` was a full scan (1-2 s per query, ~10 per question).
pgvector's HNSW index supports at most 2000 dimensions for ``vector`` but up to 4000
for ``halfvec``, so the index is built on the half-precision cast and used when
``OWASP_PGVECTOR_HALFVEC=1`` (queries must use the same expression, see
``lane_similarity.cosine_exprs``). Partial on the agent channel; a no-op on SQLite,
without the ``vector`` extension, or when the column is wider than 4000 dimensions.
Also merges the two migration heads that existed before it.

Operational note: ``CREATE INDEX CONCURRENTLY`` waits for every older open transaction,
so long-idle application sessions ("idle in transaction") can stall it; end them first.
"""

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = ("c9d0e1f2a3b4", "f5a6b7c8d9e0")
branch_labels = None
depends_on = None

INDEX_NAME = "idx_embeddings_agent_hnsw"
MAX_HALFVEC_DIM = 4000


def _column_dimension(bind) -> int:
    """Dimension of ``embeddings.embedding_vec`` (0 when absent or not a vector)."""
    row = bind.exec_driver_sql(
        "SELECT a.atttypmod FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_type t ON t.oid = a.atttypid "
        "WHERE c.relname = 'embeddings' AND a.attname = 'embedding_vec' "
        "AND t.typname = 'vector' AND NOT a.attisdropped"
    ).fetchone()
    return int(row[0]) if row and row[0] and int(row[0]) > 0 else 0


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    has_vector = bind.exec_driver_sql(
        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    dim = _column_dimension(bind) if has_vector else 0
    if not dim or dim > MAX_HALFVEC_DIM:
        return
    # CONCURRENTLY keeps the table writable while a large production index builds;
    # it cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} ON embeddings "
            f"USING hnsw ((embedding_vec::halfvec({dim})) halfvec_cosine_ops) "
            "WHERE source_channel = 'owasp_agent_meta'"
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
