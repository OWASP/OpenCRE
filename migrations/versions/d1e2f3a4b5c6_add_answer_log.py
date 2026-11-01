"""answer_log: every answer given, with an optional thumbs up/down

Revision ID: d1e2f3a4b5c6
Revises: e5f6a7b8c9d0
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "answer_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("citations", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("flags", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("rating", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("rated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_answer_log_created_at", "answer_log", ["created_at"])
    op.create_index("ix_answer_log_rating", "answer_log", ["rating"])


def downgrade():
    op.drop_index("ix_answer_log_rating", table_name="answer_log")
    op.drop_index("ix_answer_log_created_at", table_name="answer_log")
    op.drop_table("answer_log")
