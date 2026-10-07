"""admin_runtime_setting + audit for durable OIE_GRAPH_FILING_ENABLED

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
"""

from alembic import op
import sqlalchemy as sa


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_runtime_setting",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
    )
    op.create_table(
        "admin_runtime_setting_audit",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_admin_runtime_setting_audit_key",
        "admin_runtime_setting_audit",
        ["key"],
    )


def downgrade():
    op.drop_index(
        "ix_admin_runtime_setting_audit_key",
        table_name="admin_runtime_setting_audit",
    )
    op.drop_table("admin_runtime_setting_audit")
    op.drop_table("admin_runtime_setting")
