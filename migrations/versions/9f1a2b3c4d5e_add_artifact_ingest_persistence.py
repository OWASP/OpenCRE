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


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def has_unique_on_columns(table: str, columns: list) -> bool:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints(table):
        if constraint["column_names"] == columns:
            return True
    return False


def constraint_name_exists(table: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        c["name"] == constraint_name for c in inspector.get_unique_constraints(table)
    )


def _ensure_unique_constraint(table: str, name: str, columns: list) -> None:
    if has_unique_on_columns(table, columns):
        return
    # SQLite cannot ALTER ADD CONSTRAINT; batch_alter rewrites the table.
    if _is_sqlite():
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        with op.batch_alter_table(table) as batch_op:
            if constraint_name_exists(table, name):
                batch_op.drop_constraint(name, type_="unique")
            batch_op.create_unique_constraint(name, columns)
    finally:
        if _is_sqlite():
            op.execute(sa.text("PRAGMA foreign_keys=ON"))


def upgrade():
    # UniqueConstraints must be declared inside create_table: SQLite rejects
    # op.create_unique_constraint() after CREATE TABLE.
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
    else:
        _ensure_unique_constraint(
            "artifact_ingest_event",
            "uq_artifact_ingest_event_run_artifact",
            ["run_id", "artifact_id"],
        )

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
    else:
        _ensure_unique_constraint(
            "ingest_chunk",
            "uq_ingest_chunk_artifact_chunk",
            ["artifact_event_id", "chunk_id"],
        )


def downgrade():
    if table_exists("ingest_chunk"):
        op.drop_table("ingest_chunk")
    if table_exists("artifact_ingest_event"):
        op.drop_table("artifact_ingest_event")
