"""empty message

Revision ID: fffdc0652e27
Revises: 7bf4eac76958
Create Date: 2023-05-07 20:13:15.549448

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffdc0652e27"
down_revision = "7bf4eac76958"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "embeddings",
        sa.Column("embeddings", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("cre_id", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("embeddings_content", sa.String(), nullable=False),
        sa.Column("embeddings_url", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "doc_type", "cre_id", "node_id", name="uq_entry"
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("embeddings")
    # ### end Alembic commands ###
