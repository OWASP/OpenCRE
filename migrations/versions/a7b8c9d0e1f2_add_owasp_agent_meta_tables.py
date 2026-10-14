"""owasp agent meta_* index tables (meta_entity, concepts, sync_log)

Revision ID: a7b8c9d0e1f2
Revises: f3a91c07d24b

Idempotent: IndexStore.create_all may already have created meta_entity on
environments that ran the agent before this migration shipped.
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f3a91c07d24b"
branch_labels = None
depends_on = None


def _tables() -> set:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    existing = _tables()
    if "meta_entity" not in existing:
        op.create_table(
            "meta_entity",
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("fetched_at", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("kind", "key", "source"),
        )
    if "owasp_concept" not in existing:
        op.create_table(
            "owasp_concept",
            sa.Column("key", sa.String(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("evidence_urls", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("entity_keys", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("merged_into", sa.String(), nullable=False, server_default=""),
            sa.Column("source", sa.String(), nullable=False, server_default="auto"),
            sa.Column("updated_at", sa.String(), nullable=False),
        )
    if "sync_log" not in existing:
        op.create_table(
            "sync_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
        )
    if "concept_merge_audit" not in existing:
        op.create_table(
            "concept_merge_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("from_key", sa.String(), nullable=False),
            sa.Column("into_key", sa.String(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
        )


def downgrade():
    existing = _tables()
    for name in (
        "concept_merge_audit",
        "sync_log",
        "owasp_concept",
        "meta_entity",
    ):
        if name in existing:
            op.drop_table(name)
