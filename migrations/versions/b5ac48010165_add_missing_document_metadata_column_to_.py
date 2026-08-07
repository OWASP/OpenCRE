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


def upgrade():
    # Add to 'cre' table if missing
    if not column_exists("cre", "document_metadata"):
        op.add_column("cre", sa.Column("document_metadata", sa.JSON(), nullable=True))
        print("Added document_metadata to cre")
    else:
        print("Column document_metadata already exists in cre, skipping.")

    # Add to 'node' table if missing
    if not column_exists("node", "document_metadata"):
        op.add_column("node", sa.Column("document_metadata", sa.JSON(), nullable=True))
        print("Added document_metadata to node")
    else:
        print("Column document_metadata already exists in node, skipping.")


def downgrade():
    # Remove document_metadata from cre and node only if they were added by this migration
    # (i.e., they exist but we can't tell if they were pre-existing, but we can check existence)
    # For safety, we drop only if the column exists; if it existed before, this migration
    # would have skipped adding it, but we can't track that. So we drop unconditionally
    # because it's unlikely the column existed before this migration.
    # However, to be safe, we can use batch_alter_table only if the column exists.
    with op.batch_alter_table("cre") as batch_op:
        # If the column doesn't exist, drop_column will raise an error, so we must check.
        # We'll re-use column_exists but note that it's defined above.
        if column_exists("cre", "document_metadata"):
            batch_op.drop_column("document_metadata")
    with op.batch_alter_table("node") as batch_op:
        if column_exists("node", "document_metadata"):
            batch_op.drop_column("document_metadata")
