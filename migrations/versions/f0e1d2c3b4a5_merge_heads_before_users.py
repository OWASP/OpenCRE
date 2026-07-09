"""merge embeddings heads (ab12cd34ef56, 9b1c2d3e4f50) before users

No schema changes; collapses the two open heads into a single lineage so the
users migration has a single parent and ``flask db downgrade`` is unambiguous.

Revision ID: f0e1d2c3b4a5
Revises: ab12cd34ef56, 9b1c2d3e4f50
Create Date: 2026-07-08

"""

from alembic import op
import sqlalchemy as sa


revision = "f0e1d2c3b4a5"
down_revision = ("ab12cd34ef56", "9b1c2d3e4f50")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
