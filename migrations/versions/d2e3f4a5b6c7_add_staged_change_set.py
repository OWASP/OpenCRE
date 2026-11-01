"""staged_change_set + standard_snapshot for admin import staging

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e3f4a5b6c7"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "standard_snapshot",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id", sa.String(), sa.ForeignKey("import_run.id"), nullable=False
        ),
        sa.Column("standard_name", sa.String(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "run_id", "standard_name", name="uq_standard_snapshot_run_standard"
        ),
    )
    op.create_table(
        "staged_change_set",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("import_run.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("changeset_json", sa.Text(), nullable=False),
        sa.Column("has_conflicts", sa.Boolean(), nullable=False),
        sa.Column("staging_status", sa.String(), nullable=False),
        sa.Column("apply_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("staged_change_set")
    op.drop_table("standard_snapshot")
