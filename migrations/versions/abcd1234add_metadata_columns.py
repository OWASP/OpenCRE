"""add metadata columns to node and cre

Revision ID: abcd1234add
Revises: 7f27babf58e1
Create Date: 2026-03-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "abcd1234add"
down_revision = "7f27babf58e1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("node", schema=None) as batch_op:
        batch_op.add_column(sa.Column("document_metadata", sa.JSON(), nullable=True))

    with op.batch_alter_table("cre", schema=None) as batch_op:
        batch_op.add_column(sa.Column("document_metadata", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("cre", schema=None) as batch_op:
        batch_op.drop_column("document_metadata")

    with op.batch_alter_table("node", schema=None) as batch_op:
        batch_op.drop_column("document_metadata")
