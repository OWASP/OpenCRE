"""
Add embeddings.embedding_vec (pgvector) and merge dual Alembic heads.

Revision ID: c7d8e9f0a1b2
Revises: 9b1c2d3e4f50, ab12cd34ef56
Create Date: 2026-07-13

Do **not** re-embed the full corpus on Heroku/production dynos — likely
OOM-killed. This migration only: CREATE EXTENSION vector, ADD COLUMN
embedding_vec, and copy matching-dim CSV → vector. Fix missing / wrong-dim
rows offline on a high-RAM machine, then re-run / backfill.

ANN index (HNSW/IVFFlat) is intentionally deferred: opencreorg runs on
Heroku Postgres Essential-1; add a follow-up migration with
``CREATE INDEX ... USING hnsw (embedding_vec vector_cosine_ops)`` once
dims/backfill are settled and plan capacity allows.
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
    """Postgres-only: enable pgvector, add embedding_vec, backfill from CSV.

    SQLite/CI: no-op (chat/Librarian keep in-memory / CSV paths).
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


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute(sa.text("ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding_vec"))
    # Intentionally leave the `vector` extension installed (may be shared).
