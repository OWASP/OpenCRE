"""add Module B tables: harvest_input + knowledge_queue

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-07-19

harvest_input  -- Module A writes harvested chunks here (JSONB payload); B reads.
knowledge_queue -- Module B writes classified keepers here; Module C reads.
See docs/gsoc_2026_module_b/orchestrator_integration_design.md and
module_c_contract.md (v0.2).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4e5f6a7b8c9"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "harvest_input",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_run_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        # A's ChangeRecord: JSONB on Postgres, JSON elsewhere.
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_harvest_input_pipeline_run_id", "harvest_input", ["pipeline_run_id"]
    )
    op.create_index(
        "ix_harvest_input_run_status", "harvest_input", ["pipeline_run_id", "status"]
    )

    op.create_table(
        "knowledge_queue",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("chunk_id", sa.String, nullable=False),
        sa.Column("artifact_id", sa.String, nullable=False),
        sa.Column("pipeline_run_id", sa.String, nullable=False),
        sa.Column("schema_version", sa.String, nullable=False),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("source_repo", sa.String, nullable=True),
        sa.Column("source_commit_sha", sa.String, nullable=True),
        sa.Column("source_committed_at", sa.String, nullable=True),
        sa.Column("feed_url", sa.String, nullable=True),
        sa.Column("post_guid", sa.String, nullable=True),
        sa.Column("locator_kind", sa.String, nullable=False),
        sa.Column("locator_path", sa.String, nullable=False),
        sa.Column("span_index", sa.Integer, nullable=False),
        sa.Column("span_total", sa.Integer, nullable=False),
        sa.Column("span_heading_path", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("llm_label", sa.String, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("llm_reasoning", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("consumed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("content_hash", name="uq_content_hash"),
    )
    op.create_index("ix_knowledge_queue_unconsumed", "knowledge_queue", ["consumed_at"])


def downgrade():
    op.drop_table("knowledge_queue")
    op.drop_table("harvest_input")
