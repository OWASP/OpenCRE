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


def column_exists(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    # Postgres already gets embedding_vec via c7d8e9f0a1b2 (pgvector). SQLite
    # skipped that revision; add a TEXT stand-in when missing so local cache
    # paths (e.g. update-cwe.sh / make migrate-upgrade) do not fail.
    if not column_exists("embeddings", "embedding_vec"):
        op.add_column(
            "embeddings", sa.Column("embedding_vec", sa.Text(), nullable=True)
        )


def downgrade():
    # Only reverse the SQLite TEXT column. Never drop embedding_vec on
    # Postgres — that column is owned by the pgvector migration.
    if op.get_bind().dialect.name != "sqlite":
        return
    if column_exists("embeddings", "embedding_vec"):
        with op.batch_alter_table("embeddings") as batch_op:
            batch_op.drop_column("embedding_vec")
