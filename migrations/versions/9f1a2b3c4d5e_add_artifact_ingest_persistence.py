"""add artifact ingest event and chunk tables

Revision ID: 9f1a2b3c4d5e
Revises: e1f2a3b4c5d6
Create Date: 2026-07-23

"""

from alembic import op
import sqlalchemy as sa


revision = "9f1a2b3c4d5e"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "artifact_ingest_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("harvest_mode", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("locator_json", sa.Text(), nullable=False),
        sa.Column("artifact_json", sa.Text(), nullable=False),
        sa.Column("harvest_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["import_run.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    op.create_unique_constraint(
        "uq_artifact_ingest_event_run_artifact",
        "artifact_ingest_event",
        ["run_id", "artifact_id"],
    )

    op.create_table(
        "ingest_chunk",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_event_id", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("span_json", sa.Text(), nullable=False),
        sa.Column("delta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_event_id"],
            ["artifact_ingest_event.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    op.create_unique_constraint(
        "uq_ingest_chunk_artifact_chunk",
        "ingest_chunk",
        ["artifact_event_id", "chunk_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_ingest_chunk_artifact_chunk",
        "ingest_chunk",
        type_="unique",
    )
    op.drop_table("ingest_chunk")
    op.drop_constraint(
        "uq_artifact_ingest_event_run_artifact",
        "artifact_ingest_event",
        type_="unique",
    )
    op.drop_table("artifact_ingest_event")
