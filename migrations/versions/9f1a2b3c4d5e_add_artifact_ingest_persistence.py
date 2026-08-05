"""add artifact ingest event and chunk tables

Revision ID: 9f1a2b3c4d5e
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23

"""

from alembic import op
import sqlalchemy as sa

revision = "9f1a2b3c4d5e"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

def table_exists(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()

def constraint_exists(table, constraint_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    constraints = inspector.get_unique_constraints(table)
    return any(c['name'] == constraint_name for c in constraints)

def upgrade():
    # Create artifact_ingest_event only if it doesn't exist
    if not table_exists("artifact_ingest_event"):
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
            sa.UniqueConstraint("run_id", "artifact_id", name="uq_artifact_ingest_event_run_artifact"),
        )
    else:
        print("Table artifact_ingest_event already exists, checking constraints...")
        # Ensure the unique constraint exists
        if not constraint_exists("artifact_ingest_event", "uq_artifact_ingest_event_run_artifact"):
            print("Adding missing unique constraint to artifact_ingest_event...")
            with op.batch_alter_table("artifact_ingest_event") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_artifact_ingest_event_run_artifact",
                    ["run_id", "artifact_id"]
                )

    # Create ingest_chunk only if it doesn't exist
    if not table_exists("ingest_chunk"):
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
            sa.UniqueConstraint("artifact_event_id", "chunk_id", name="uq_ingest_chunk_artifact_chunk"),
        )
    else:
        print("Table ingest_chunk already exists, checking constraints...")
        # Ensure the unique constraint exists
        if not constraint_exists("ingest_chunk", "uq_ingest_chunk_artifact_chunk"):
            print("Adding missing unique constraint to ingest_chunk...")
            with op.batch_alter_table("ingest_chunk") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_ingest_chunk_artifact_chunk",
                    ["artifact_event_id", "chunk_id"]
                )

def downgrade():
    # Drop tables in reverse order; constraints are dropped automatically with the tables.
    op.drop_table("ingest_chunk")
    op.drop_table("artifact_ingest_event")