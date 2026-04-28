"""add embedding model metadata columns

Revision ID: ab12cd34ef56
Revises: e1f2a3b4c5d6
Create Date: 2026-04-28

"""

from alembic import op
import sqlalchemy as sa


revision = "ab12cd34ef56"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "embeddings",
        sa.Column("embedding_model_id", sa.String(), nullable=True),
    )
    op.add_column(
        "embeddings",
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("embeddings", "embedding_dim")
    op.drop_column("embeddings", "embedding_model_id")
