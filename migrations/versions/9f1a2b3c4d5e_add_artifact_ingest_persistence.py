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


def has_unique_on_columns(table, columns):
    """Return True if any unique constraint (named or unnamed) exists on exactly these columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    constraints = inspector.get_unique_constraints(table)
    for c in constraints:
        if c["column_names"] == columns:
            return True
    return False


def constraint_name_exists(table, constraint_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return any(
        c["name"] == constraint_name for c in inspector.get_unique_constraints(table)
    )


def tracking_record_exists(revision, table_name):
    """Check if this migration created the given table."""
    conn = op.get_bind()
    if not table_exists("_migration_tracking"):
        return False
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM _migration_tracking WHERE revision = :rev AND table_name = :tbl"
        ),
        {"rev": revision, "tbl": table_name},
    )
    return result.first() is not None


def add_tracking_record(revision, table_name):
    if not table_exists("_migration_tracking"):
        op.create_table(
            "_migration_tracking",
            sa.Column("revision", sa.String, primary_key=True),
            sa.Column("table_name", sa.String, primary_key=True),
        )
    op.execute(
        sa.text(
            "INSERT INTO _migration_tracking (revision, table_name) VALUES (:rev, :tbl)"
        ),
        {"rev": revision, "tbl": table_name},
    )


def remove_tracking_record(revision, table_name):
    if table_exists("_migration_tracking"):
        op.execute(
            sa.text(
                "DELETE FROM _migration_tracking WHERE revision = :rev AND table_name = :tbl"
            ),
            {"rev": revision, "tbl": table_name},
        )


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
            sa.UniqueConstraint(
                "run_id", "artifact_id", name="uq_artifact_ingest_event_run_artifact"
            ),
        )
        add_tracking_record(revision, "artifact_ingest_event")
    else:
        # Ensure the unique constraint exists
        if not has_unique_on_columns(
            "artifact_ingest_event", ["run_id", "artifact_id"]
        ):
            # Temporarily disable foreign keys for SQLite because we may drop the parent table
            op.execute("PRAGMA foreign_keys=OFF")
            try:
                with op.batch_alter_table("artifact_ingest_event") as batch_op:
                    if constraint_name_exists(
                        "artifact_ingest_event",
                        "uq_artifact_ingest_event_run_artifact",
                    ):
                        batch_op.drop_constraint(
                            "uq_artifact_ingest_event_run_artifact", type_="unique"
                        )
                    batch_op.create_unique_constraint(
                        "uq_artifact_ingest_event_run_artifact",
                        ["run_id", "artifact_id"],
                    )
            finally:
                op.execute("PRAGMA foreign_keys=ON")

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
            sa.UniqueConstraint(
                "artifact_event_id",
                "chunk_id",
                name="uq_ingest_chunk_artifact_chunk",
            ),
        )
        add_tracking_record(revision, "ingest_chunk")
    else:
        if not has_unique_on_columns("ingest_chunk", ["artifact_event_id", "chunk_id"]):
            with op.batch_alter_table("ingest_chunk") as batch_op:
                if constraint_name_exists(
                    "ingest_chunk", "uq_ingest_chunk_artifact_chunk"
                ):
                    batch_op.drop_constraint(
                        "uq_ingest_chunk_artifact_chunk", type_="unique"
                    )
                batch_op.create_unique_constraint(
                    "uq_ingest_chunk_artifact_chunk",
                    ["artifact_event_id", "chunk_id"],
                )


def downgrade():
    # Drop only tables that were created by this migration
    if tracking_record_exists(revision, "ingest_chunk"):
        op.drop_table("ingest_chunk")
        remove_tracking_record(revision, "ingest_chunk")

    if tracking_record_exists(revision, "artifact_ingest_event"):
        op.drop_table("artifact_ingest_event")
        remove_tracking_record(revision, "artifact_ingest_event")
