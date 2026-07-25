"""add harvester_checkpoint table

Revision ID: d4e5f6a7b8c9
Revises: 9f1a2b3c4d5e
Create Date: 2026-07-25

"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "9f1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "harvester_checkpoint",
        sa.Column("repository_id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repository", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("last_processed_commit", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "owner",
            "repository",
            "branch",
            name="uq_harvester_checkpoint_canonical_source",
        ),
    )


def downgrade():
    op.drop_table("harvester_checkpoint")
