"""admin panel tables: ingestion_target, admin_pipeline_event

Revision ID: f8a9b0c1d2e3
Revises: 967016ee10fa
"""

from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "967016ee10fa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingestion_target",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "admin_pipeline_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_pipeline_event_run", "admin_pipeline_event", ["run_id"])


def downgrade():
    op.drop_index("ix_admin_pipeline_event_run", table_name="admin_pipeline_event")
    op.drop_table("admin_pipeline_event")
    op.drop_table("ingestion_target")
