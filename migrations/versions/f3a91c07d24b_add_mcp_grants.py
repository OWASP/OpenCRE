"""add mcp_grants table for MCP v2 authenticated tools (issue #1003)

Google's device flow only carries ``openid email profile``, so OpenCRE scopes
cannot live in the token and are recorded per user here instead.

Revision ID: f3a91c07d24b
Revises: 967016ee10fa
Create Date: 2026-09-29

"""

from alembic import op
import sqlalchemy as sa


revision = "f3a91c07d24b"
down_revision = "967016ee10fa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_grants",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "user_id",
            sa.String,
            sa.ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("user_id", "scope", name="uq_mcp_grants"),
    )


def downgrade():
    op.drop_table("mcp_grants")
