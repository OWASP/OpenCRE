"""add oie_run

Revision ID: b8c9d0e1f2a3
Revises: 967016ee10fa
Create Date: 2026-10-05

oie_run -- one row per scheduled OIE job run (``<job>-<slot>``), the audit trail
behind the admin run pages. Unique on (job, slot) so a replayed tick reuses its
row.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b8c9d0e1f2a3"
down_revision = "967016ee10fa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oie_run",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("job", sa.String, nullable=False),
        sa.Column("slot", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("trigger", sa.String, nullable=False),
        sa.Column("dry_run", sa.Boolean, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column(
            "summary",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.UniqueConstraint("job", "slot", name="uq_oie_run_job_slot"),
    )
    op.create_index("ix_oie_run_job_started", "oie_run", ["job", "started_at"])


def downgrade():
    op.drop_index("ix_oie_run_job_started", table_name="oie_run")
    op.drop_table("oie_run")
