"""add document_metadata to cre and node

Revision ID: 055dbd9f8bfe
Revises: d4e5f6a7b8c9
Create Date: 2026-08-06 00:13:49.191527

"""

from alembic import op
import sqlalchemy as sa

revision = "055dbd9f8bfe"
down_revision = "d4e5f6a7b8c9"  # or whatever the current head is
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
        op.add_column("cre", sa.Column("document_metadata", sa.Text(), nullable=True))
        print("Added document_metadata to cre")
    else:
        print("Column document_metadata already exists in cre, skipping.")

    # Add to 'node' table if missing
    if not column_exists("node", "document_metadata"):
        op.add_column("node", sa.Column("document_metadata", sa.Text(), nullable=True))
        print("Added document_metadata to node")
    else:
        print("Column document_metadata already exists in node, skipping.")


def downgrade():
    # Remove document_metadata from cre and node using SQLite batch pattern
    with op.batch_alter_table("cre") as batch_op:
        batch_op.drop_column("document_metadata")
    with op.batch_alter_table("node") as batch_op:
        batch_op.drop_column("document_metadata")
