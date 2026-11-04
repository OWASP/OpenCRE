"""add knowledge_claim table (Phase 5 RAG/OIE parity)

Revision ID: a1b2c3d4e5f7
Revises: d7e8f9a0b1c2
Create Date: 2026-11-03

Additive only. Claims are reviewable extracts — never unsupervised CRE graph writes.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f7"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_claim",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_claim_status", "knowledge_claim", ["status"])
    op.create_index("ix_knowledge_claim_source_ref", "knowledge_claim", ["source_ref"])


def downgrade():
    op.drop_index("ix_knowledge_claim_source_ref", table_name="knowledge_claim")
    op.drop_index("ix_knowledge_claim_status", table_name="knowledge_claim")
    op.drop_table("knowledge_claim")
