"""
Add embeddings.embedding_vec (pgvector), backfill from CSV, drop CSV column.

Revision ID: c7d8e9f0a1b2
Revises: 9b1c2d3e4f50, ab12cd34ef56
Create Date: 2026-07-13

Do **not** re-embed the full corpus on Heroku/production dynos — likely
OOM-killed. This migration only: CREATE EXTENSION vector, ADD COLUMN
embedding_vec, copy matching-dim CSV → vector, then DROP the legacy CSV
``embeddings`` column. Fix missing / wrong-dim rows offline on a high-RAM
machine before deploying.

ANN index (HNSW/IVFFlat) is intentionally deferred: opencreorg runs on
Heroku Postgres Essential-1; add a follow-up migration with
``CREATE INDEX ... USING hnsw (embedding_vec vector_cosine_ops)`` once
plan capacity allows.
"""

from alembic import op
import sqlalchemy as sa

from application.database.pgvector_utils import (
    HEROKU_REEMBED_WARNING,
    backfill_embedding_vec,
    require_single_embedding_dim,
)

# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = ("9b1c2d3e4f50", "ab12cd34ef56")
branch_labels = None
depends_on = None


def upgrade():
    """Postgres-only: pgvector column, CSV backfill, drop legacy CSV column.

    SQLite/CI: no-op (ORM maps ``embedding_vec`` as Text for create_all).
    """
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # See module docstring / HEROKU_REEMBED_WARNING — no LLM re-embed here.
    _ = HEROKU_REEMBED_WARNING

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    dim = require_single_embedding_dim(conn)
    op.execute(
        sa.text(
            f"ALTER TABLE embeddings "
            f"ADD COLUMN IF NOT EXISTS embedding_vec vector({int(dim)})"
        )
    )
    backfill_embedding_vec(conn, dim)

    # Refuse to drop CSV if any row still lacks a vector (should be empty after
    # a clean backfill; wrong-dim / empty CSV rows must be fixed offline).
    leftover = conn.execute(
        sa.text("SELECT COUNT(*) FROM embeddings WHERE embedding_vec IS NULL")
    ).scalar()
    if leftover:
        raise RuntimeError(
            f"{leftover} embeddings row(s) still have NULL embedding_vec after "
            "backfill — refuse to DROP CSV column. Reconcile offline "
            "(do not re-embed on Heroku). " + HEROKU_REEMBED_WARNING
        )

    op.execute(sa.text("ALTER TABLE embeddings DROP COLUMN IF EXISTS embeddings"))
    op.execute(
        sa.text("ALTER TABLE embeddings ALTER COLUMN embedding_vec SET NOT NULL")
    )


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    # Restore CSV from vector text form ``[1,2,3]`` → ``1,2,3``.
    op.execute(
        sa.text("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS embeddings TEXT")
    )
    op.execute(
        sa.text(
            """
            UPDATE embeddings
            SET embeddings = trim(both '[]' FROM replace(embedding_vec::text, ' ', ''))
            WHERE embedding_vec IS NOT NULL
              AND (embeddings IS NULL OR btrim(embeddings) = '')
            """
        )
    )
    op.execute(
        sa.text("ALTER TABLE embeddings ALTER COLUMN embedding_vec DROP NOT NULL")
    )
    op.execute(sa.text("ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding_vec"))
    # Intentionally leave the `vector` extension installed (may be shared).
