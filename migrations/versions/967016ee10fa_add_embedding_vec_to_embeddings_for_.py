"""add embedding_vec to embeddings for SQLite

Revision ID: 967016ee10fa
Revises: 055dbd9f8bfe
Create Date: 2026-08-06 00:13:49.191527

"""

from alembic import op
import sqlalchemy as sa

revision = "967016ee10fa"
down_revision = "055dbd9f8bfe"  # <-- set this to the head revision you found
branch_labels = None
depends_on = None


def column_exists(table, column):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade():
    if not column_exists("embeddings", "embedding_vec"):
        op.add_column(
            "embeddings", sa.Column("embedding_vec", sa.Text(), nullable=True)
        )
        print("Added embedding_vec to embeddings")
    else:
        print("Column embedding_vec already exists in embeddings, skipping.")


def downgrade():
    # Remove embedding_vec from embeddings using SQLite batch pattern
    with op.batch_alter_table("embeddings") as batch_op:
        batch_op.drop_column("embedding_vec")
