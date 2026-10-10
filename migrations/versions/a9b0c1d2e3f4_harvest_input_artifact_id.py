"""Promote harvest_input.artifact_id (+ source_repo) for OIE RQ fan-out.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

from alembic import op
import sqlalchemy as sa


revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("harvest_input") as batch_op:
        batch_op.add_column(sa.Column("artifact_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_repo", sa.String(), nullable=True))

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE harvest_input
                SET artifact_id = COALESCE(payload->>'artifact_id', ''),
                    source_repo = payload->'source'->>'repo'
                WHERE artifact_id IS NULL
                """
            )
        )
    else:
        # SQLite JSON1: json_extract
        op.execute(
            sa.text(
                """
                UPDATE harvest_input
                SET artifact_id = COALESCE(json_extract(payload, '$.artifact_id'), ''),
                    source_repo = json_extract(payload, '$.source.repo')
                WHERE artifact_id IS NULL
                """
            )
        )

    with op.batch_alter_table("harvest_input") as batch_op:
        batch_op.alter_column(
            "artifact_id",
            existing_type=sa.String(),
            nullable=False,
            server_default="",
        )
        batch_op.create_index(
            "ix_harvest_input_run_status_artifact",
            ["pipeline_run_id", "status", "artifact_id"],
        )


def downgrade():
    with op.batch_alter_table("harvest_input") as batch_op:
        batch_op.drop_index("ix_harvest_input_run_status_artifact")
        batch_op.drop_column("source_repo")
        batch_op.drop_column("artifact_id")
