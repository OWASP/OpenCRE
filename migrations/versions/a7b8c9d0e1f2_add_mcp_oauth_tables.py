"""mcp_oauth_clients / mcp_oauth_refresh_tokens: Google sign-in for the remote MCP server

Revision ID: a7b8c9d0e1f2
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(), primary_key=True),
        sa.Column("info_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "mcp_oauth_refresh_tokens",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_mcp_oauth_refresh_tokens_user_id", "mcp_oauth_refresh_tokens", ["user_id"]
    )


def downgrade():
    op.drop_index(
        "ix_mcp_oauth_refresh_tokens_user_id", table_name="mcp_oauth_refresh_tokens"
    )
    op.drop_table("mcp_oauth_refresh_tokens")
    op.drop_table("mcp_oauth_clients")
