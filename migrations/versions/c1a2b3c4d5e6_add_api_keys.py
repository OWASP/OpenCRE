"""api_keys + api_key_audit_log for JWT API tokens

Revision ID: c1a2b3c4d5e6
Revises: a9b0c1d2e3f4
"""

from alembic import op
import sqlalchemy as sa


revision = "c1a2b3c4d5e6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_keys",
        sa.Column("jti", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_table(
        "api_key_audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("jti", sa.String(), sa.ForeignKey("api_keys.jti"), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_api_key_audit_log_jti", "api_key_audit_log", ["jti"])
    op.create_index(
        "ix_api_key_audit_log_created_at", "api_key_audit_log", ["created_at"]
    )


def downgrade():
    op.drop_index("ix_api_key_audit_log_created_at", table_name="api_key_audit_log")
    op.drop_index("ix_api_key_audit_log_jti", table_name="api_key_audit_log")
    op.drop_table("api_key_audit_log")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")
