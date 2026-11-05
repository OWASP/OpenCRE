"""add embedding_vec to embeddings for SQLite

Revision ID: 967016ee10fa
Revises: e7c3b91d5a24
Create Date: 2026-08-06 00:13:49.191527

"""

from alembic import op
import sqlalchemy as sa


revision = "967016ee10fa"
down_revision = "e7c3b91d5a24"
branch_labels = None
depends_on = None


def column_exists(table: str, column: str) -> bool:
    """Return True if the given column exists in the specified table."""
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    """
    Add embedding_vec as a TEXT column for SQLite if it is missing.

    PostgreSQL already gets this column from the pgvector migration
    (c7d8e9f0a1b2). SQLite skips that revision, so this fills the gap to
    prevent errors in local cache paths (e.g., update-cwe.sh).
    """
    # Postgres already gets embedding_vec via c7d8e9f0a1b2 (pgvector). SQLite
    # skipped that revision; add a TEXT stand-in when missing so local cache
    # paths (e.g. update-cwe.sh / make migrate-upgrade) do not fail.
    if not column_exists("embeddings", "embedding_vec"):
        op.add_column(
            "embeddings", sa.Column("embedding_vec", sa.Text(), nullable=True)
        )


def downgrade():
    """
    Remove the SQLite TEXT embedding_vec column if present.

    This never runs on PostgreSQL because the pgvector migration owns that
    column there. For SQLite, it reverses only what this migration added.
    """
    # Only reverse the SQLite TEXT column. Never drop embedding_vec on
    # Postgres — that column is owned by the pgvector migration.
    if op.get_bind().dialect.name != "sqlite":
        return
    if column_exists("embeddings", "embedding_vec"):
        with op.batch_alter_table("embeddings") as batch_op:
            batch_op.drop_column("embedding_vec")
