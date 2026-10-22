"""oie_llm_cache for librarian LLM response reuse (shortlist/edition/neighbor/safety)

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
"""

from alembic import op
import sqlalchemy as sa


revision = "e4f5a6b7c8d9"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oie_llm_cache",
        sa.Column("kind", sa.String(), primary_key=True, nullable=False),
        sa.Column("cache_key", sa.String(), primary_key=True, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_oie_llm_cache_kind", "oie_llm_cache", ["kind"])


def downgrade():
    op.drop_index("ix_oie_llm_cache_kind", table_name="oie_llm_cache")
    op.drop_table("oie_llm_cache")
