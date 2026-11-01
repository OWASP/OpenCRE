"""Add embeddings.source_channel for multi-lane chat routing.

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2

Channels:
  - cre_graph: CRE definition embeddings
  - corpus: Standard/Tool/node document embeddings
  - owasp_agent_meta: OWASP community metadata (+ optional evidence notes)
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("embeddings")}
    if "source_channel" not in cols:
        op.add_column(
            "embeddings",
            sa.Column("source_channel", sa.String(), nullable=True),
        )
    # Backfill existing rows (idempotent).
    op.execute(
        sa.text(
            "UPDATE embeddings SET source_channel = 'cre_graph' "
            "WHERE source_channel IS NULL AND doc_type = 'CRE'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE embeddings SET source_channel = 'corpus' "
            "WHERE source_channel IS NULL AND (doc_type IS NULL OR doc_type <> 'CRE')"
        )
    )


def downgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("embeddings")}
    if "source_channel" in cols:
        op.drop_column("embeddings", "source_channel")
