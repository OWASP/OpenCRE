"""add user_standards and user_standard_sections for MyOpenCRE mapping (#965)

RFC user-auth-myopencre TODO 2: a user-owned standard and its sections, with
the mapping job's outcome per section. ``cre_db_id`` is a soft reference to
the CRE row (validated at write time), never a foreign key, so the graph
layer and the user layer stay decoupled.

Revision ID: c4a1e7b2d9f0
Revises: f3a91c07d24b
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa

revision = "c4a1e7b2d9f0"
down_revision = "f3a91c07d24b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_standards",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "user_id",
            sa.String,
            sa.ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_user_standards_user_name"),
    )
    op.create_table(
        "user_standard_sections",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "standard_id",
            sa.String,
            sa.ForeignKey("user_standards.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_id", sa.String, nullable=False),
        sa.Column("section_text", sa.Text, nullable=False),
        sa.Column("cre_db_id", sa.String, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint(
            "standard_id", "section_id", name="uq_user_standard_sections_section"
        ),
    )
    op.create_index(
        "ix_user_standard_sections_status",
        "user_standard_sections",
        ["standard_id", "status"],
    )
    op.create_index(
        "ix_user_standard_sections_cre",
        "user_standard_sections",
        ["standard_id", "cre_db_id"],
    )


def downgrade():
    op.drop_index("ix_user_standard_sections_cre", table_name="user_standard_sections")
    op.drop_index(
        "ix_user_standard_sections_status", table_name="user_standard_sections"
    )
    op.drop_table("user_standard_sections")
    op.drop_table("user_standards")
