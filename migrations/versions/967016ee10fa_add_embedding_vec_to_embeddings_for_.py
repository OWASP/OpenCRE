"""add embedding_vec to embeddings for SQLite

Revision ID: 967016ee10fa
Revises: b5ac48010165
Create Date: 2026-08-06 00:13:49.191527

"""

from alembic import op
import sqlalchemy as sa

revision = "967016ee10fa"
down_revision = "b5ac48010165"
branch_labels = None
depends_on = None


def column_exists(table, column):
    """Check if a column exists in the given table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade():
    """Add embedding_vec as a TEXT column for SQLite if it doesn't already exist."""
    if not column_exists("embeddings", "embedding_vec"):
        op.add_column(
            "embeddings", sa.Column("embedding_vec", sa.Text(), nullable=True)
        )


def downgrade():
    """Remove embedding_vec from embeddings if it was added by this migration."""
    with op.batch_alter_table("embeddings") as batch_op:
        if column_exists("embeddings", "embedding_vec"):
            batch_op.drop_column("embedding_vec")