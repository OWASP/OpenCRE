"""add import_runs table for Module C (Step 6)

Revision ID: e1f2a3b4c5d6
Revises: 7f27babf58e1
Create Date: 2026-03-21

"""

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "7f27babf58e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_run",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("import_run")
