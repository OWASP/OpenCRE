"""make embeddings foreign keys nullable with surrogate primary key

Revision ID: 9b1c2d3e4f50
Revises: e1f2a3b4c5d6
Create Date: 2026-04-19

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b1c2d3e4f50"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        # Handle both legacy composite PK names and environments where the table
        # already exists with a different PK from prior bootstrap/sync paths.
        pk_name = conn.execute(
            sa.text(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.contype = 'p'
                  AND n.nspname = 'public'
                  AND t.relname = 'embeddings'
                LIMIT 1
                """
            )
        ).scalar()
        if pk_name:
            op.execute(
                sa.text(
                    f'ALTER TABLE public.embeddings DROP CONSTRAINT IF EXISTS "{pk_name}"'
                )
            )
        op.execute('ALTER TABLE public.embeddings DROP CONSTRAINT IF EXISTS "uq_entry"')
        op.execute("ALTER TABLE public.embeddings ADD COLUMN IF NOT EXISTS id VARCHAR")
        op.execute(
            "UPDATE public.embeddings "
            "SET id = md5(random()::text || clock_timestamp()::text) WHERE id IS NULL"
        )
        op.execute(
            "ALTER TABLE public.embeddings "
            "ALTER COLUMN id SET DEFAULT md5(random()::text || clock_timestamp()::text)"
        )
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN id SET NOT NULL")
        has_pk = conn.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.contype = 'p'
                  AND n.nspname = 'public'
                  AND t.relname = 'embeddings'
                LIMIT 1
                """
            )
        ).scalar()
        if not has_pk:
            op.execute(
                "ALTER TABLE public.embeddings ADD CONSTRAINT pk_embeddings_id PRIMARY KEY (id)"
            )
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN embeddings SET NOT NULL")
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN doc_type SET NOT NULL")
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN cre_id DROP NOT NULL")
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN node_id DROP NOT NULL")
        op.execute(
            "UPDATE public.embeddings SET cre_id = NULL WHERE cre_id IS NOT NULL AND btrim(cre_id) = ''"
        )
        op.execute(
            "UPDATE public.embeddings SET node_id = NULL WHERE node_id IS NOT NULL AND btrim(node_id) = ''"
        )
        op.execute(
            "UPDATE public.embeddings SET embeddings_content = NULL "
            "WHERE embeddings_content IS NOT NULL AND btrim(embeddings_content) = ''"
        )
        op.execute(
            "UPDATE public.embeddings SET embeddings_url = NULL "
            "WHERE embeddings_url IS NOT NULL AND btrim(embeddings_url) = ''"
        )
    else:
        with op.batch_alter_table("embeddings", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "id",
                    sa.String(),
                    nullable=True,
                    server_default=sa.text("lower(hex(randomblob(16)))"),
                )
            )
            batch_op.drop_constraint("uq_entry", type_="primary")
            batch_op.alter_column(
                "embeddings", existing_type=sa.String(), nullable=False
            )
            batch_op.alter_column("doc_type", existing_type=sa.String(), nullable=False)
            batch_op.alter_column("cre_id", existing_type=sa.String(), nullable=True)
            batch_op.alter_column("node_id", existing_type=sa.String(), nullable=True)
            batch_op.alter_column(
                "embeddings_content", existing_type=sa.String(), nullable=True
            )
            batch_op.alter_column(
                "embeddings_url", existing_type=sa.String(), nullable=True
            )
            batch_op.create_primary_key("pk_embeddings_id", ["id"])

        op.execute(
            "UPDATE embeddings SET id = lower(hex(randomblob(16))) WHERE id IS NULL"
        )
        op.execute(
            "UPDATE embeddings SET cre_id = NULL WHERE trim(ifnull(cre_id, '')) = ''"
        )
        op.execute(
            "UPDATE embeddings SET node_id = NULL WHERE trim(ifnull(node_id, '')) = ''"
        )
        op.execute(
            "UPDATE embeddings SET embeddings_content = NULL "
            "WHERE trim(ifnull(embeddings_content, '')) = ''"
        )
        op.execute(
            "UPDATE embeddings SET embeddings_url = NULL "
            "WHERE trim(ifnull(embeddings_url, '')) = ''"
        )


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute("UPDATE public.embeddings SET cre_id = '' WHERE cre_id IS NULL")
        op.execute("UPDATE public.embeddings SET node_id = '' WHERE node_id IS NULL")
        op.execute(
            "UPDATE public.embeddings SET embeddings_content = '' WHERE embeddings_content IS NULL"
        )
        op.execute(
            "UPDATE public.embeddings SET embeddings_url = '' WHERE embeddings_url IS NULL"
        )
        op.execute(
            "ALTER TABLE public.embeddings DROP CONSTRAINT IF EXISTS pk_embeddings_id"
        )
        op.execute("ALTER TABLE public.embeddings DROP COLUMN IF EXISTS id")
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN cre_id SET NOT NULL")
        op.execute("ALTER TABLE public.embeddings ALTER COLUMN node_id SET NOT NULL")
        op.execute(
            "ALTER TABLE public.embeddings ADD CONSTRAINT uq_entry PRIMARY KEY (doc_type, cre_id, node_id)"
        )
    else:
        with op.batch_alter_table("embeddings", recreate="always") as batch_op:
            batch_op.drop_constraint("pk_embeddings_id", type_="primary")
            batch_op.drop_column("id")
            batch_op.alter_column("cre_id", existing_type=sa.String(), nullable=False)
            batch_op.alter_column("node_id", existing_type=sa.String(), nullable=False)
            batch_op.alter_column(
                "embeddings_content", existing_type=sa.String(), nullable=False
            )
            batch_op.alter_column(
                "embeddings_url", existing_type=sa.String(), nullable=False
            )
            batch_op.create_primary_key("uq_entry", ["doc_type", "cre_id", "node_id"])
