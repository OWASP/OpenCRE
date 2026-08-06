"""add missing document_metadata column to node and cre

Revision ID: b5ac48010165
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24 22:19:01.724833

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "b5ac48010165"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    # Defensive: some environments (e.g. production) already have this column
    # applied out-of-band without a corresponding migration ever being
    # committed, so this must not assume a clean "column doesn't exist" state.
    inspector = inspect(op.get_bind())
    node_columns = {c["name"] for c in inspector.get_columns("node")}
    cre_columns = {c["name"] for c in inspector.get_columns("cre")}

    if "document_metadata" not in node_columns:
        with op.batch_alter_table("node", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("document_metadata", sa.JSON(), nullable=True)
            )

    if "document_metadata" not in cre_columns:
        with op.batch_alter_table("cre", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("document_metadata", sa.JSON(), nullable=True)
            )


def downgrade():
    # Intentional no-op: upgrade() only adds this column where it was
    # missing, so on environments where it pre-existed (e.g. production,
    # applied out-of-band) this migration never created it. Unconditionally
    # dropping it here would destroy that pre-existing data on downgrade.
    # There is no reliable way to tell "did *this* migration add the
    # column" apart from "did it already exist," so the safe choice is to
    # leave the column alone rather than risk deleting real data.
    pass
