"""add Module C output table: decision_queue

Revision ID: e7c3b91d5a24
Revises: b5ac48010165
Create Date: 2026-08-13

decision_queue -- Module C writes one row per decided chunk; Module D reads the
rows it cares about and sets consumed_at. The C -> D counterpart of
knowledge_queue, and deliberately the same shape of handoff.

Both outcomes share the table, separated by `status` (linked | review_required),
exactly as Module B puts KNOWLEDGE and UNCERTAIN in one queue and lets its
readers filter. `envelope` holds the whole RFC LinkProposal / ReviewItem so a
decision stays explainable; the columns beside it are projections for querying.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7c3b91d5a24"
down_revision = "b5ac48010165"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "decision_queue",
        sa.Column("id", sa.String, primary_key=True),
        # provenance, carried verbatim from Module A through B
        sa.Column("chunk_id", sa.String, nullable=False),
        sa.Column("artifact_id", sa.String, nullable=False),
        sa.Column("pipeline_run_id", sa.String, nullable=False),
        sa.Column("schema_version", sa.String, nullable=False),
        # B's label on the chunk the decision was made from
        sa.Column("source_label", sa.String, nullable=True),
        # C's verdict
        sa.Column("status", sa.String, nullable=False),
        sa.Column("reason_code", sa.String, nullable=True),
        sa.Column("review_id", sa.String, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        # the full RFC envelope: JSONB on Postgres, JSON elsewhere
        sa.Column(
            "envelope",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("consumed_at", sa.DateTime, nullable=True),
        # One decision per chunk per run: replaying a run must not double-write.
        sa.UniqueConstraint(
            "chunk_id", "pipeline_run_id", name="uq_decision_chunk_run"
        ),
    )
    op.create_index("ix_decision_queue_unconsumed", "decision_queue", ["consumed_at"])
    op.create_index(
        "ix_decision_queue_run_status", "decision_queue", ["pipeline_run_id", "status"]
    )


def downgrade():
    op.drop_index("ix_decision_queue_run_status", table_name="decision_queue")
    op.drop_index("ix_decision_queue_unconsumed", table_name="decision_queue")
    op.drop_table("decision_queue")
