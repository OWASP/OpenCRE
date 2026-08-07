"""add missing document_metadata column to node and cre

Revision ID: b5ac48010165
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24 22:19:01.724833

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b5ac48010165"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def column_exists(table, column):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def table_exists(table):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def tracking_record_exists(revision, table_name, column_name):
    conn = op.get_bind()
    if not table_exists("_migration_tracking"):
        return False
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM _migration_tracking WHERE revision = :rev AND table_name = :tbl AND column_name = :col"
        ),
        {"rev": revision, "tbl": table_name, "col": column_name},
    )
    return result.first() is not None


def add_tracking_record(revision, table_name, column_name):
    if not table_exists("_migration_tracking"):
        op.create_table(
            "_migration_tracking",
            sa.Column("revision", sa.String, primary_key=True),
            sa.Column("table_name", sa.String, primary_key=True),
            sa.Column("column_name", sa.String, primary_key=True),
        )
    op.execute(
        sa.text(
            "INSERT INTO _migration_tracking (revision, table_name, column_name) VALUES (:rev, :tbl, :col)"
        ),
        {"rev": revision, "tbl": table_name, "col": column_name},
    )


def remove_tracking_record(revision, table_name, column_name):
    if table_exists("_migration_tracking"):
        op.execute(
            sa.text(
                "DELETE FROM _migration_tracking WHERE revision = :rev AND table_name = :tbl AND column_name = :col"
            ),
            {"rev": revision, "tbl": table_name, "col": column_name},
        )


def upgrade():
    # Add to 'cre' table if missing
    if not column_exists("cre", "document_metadata"):
        op.add_column("cre", sa.Column("document_metadata", sa.JSON(), nullable=True))
        add_tracking_record(revision, "cre", "document_metadata")

    # Add to 'node' table if missing
    if not column_exists("node", "document_metadata"):
        op.add_column("node", sa.Column("document_metadata", sa.JSON(), nullable=True))
        add_tracking_record(revision, "node", "document_metadata")


def downgrade():
    # Drop only columns that were added by this migration (tracked)
    if tracking_record_exists(revision, "cre", "document_metadata"):
        with op.batch_alter_table("cre") as batch_op:
            if column_exists("cre", "document_metadata"):
                batch_op.drop_column("document_metadata")
        remove_tracking_record(revision, "cre", "document_metadata")

    if tracking_record_exists(revision, "node", "document_metadata"):
        with op.batch_alter_table("node") as batch_op:
            if column_exists("node", "document_metadata"):
                batch_op.drop_column("document_metadata")
        remove_tracking_record(revision, "node", "document_metadata")
