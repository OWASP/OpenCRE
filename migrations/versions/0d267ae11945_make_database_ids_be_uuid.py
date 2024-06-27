"""make database ids be uuid instead of incremental ints

Revision ID: 0d267ae11945
Revises: 455f052a44ea
Create Date: 2022-04-03 16:05:31.487481

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import engine_from_config, text
from application.database.db import generate_uuid
from random import randint

# revision identifiers, used by Alembic.
revision = "0d267ae11945"
down_revision = "455f052a44ea"
branch_labels = None
depends_on = None
temp_table_number = randint(1, 100)


def copy_tables(cre_table, node_table, cre_link_table, cre_node_link_table):
    config = op.get_context().config
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy."
    )
    connection = op.get_bind()
    nodes = connection.execute(
        text(
            "Select id,name,section,subsection,link,ntype,tags,version,description from node"
        )
    )
    nodes_data = nodes.fetchall() if nodes else []

    cre = connection.execute(
        text("Select id,name,description,external_id,tags from cre")
    )
    cre_data = cre.fetchall() if cre else []

    cre_link = connection.execute(text('Select type, "group" ,cre from cre_links'))
    cre_link_data = cre_link.fetchall() if cre_link else []

    cre_node_link = connection.execute(
        text("Select type, cre, node from cre_node_links")
    )
    cre_node_link_data = cre_node_link.fetchall() if cre_node_link else []

    nodes = [
        {
            "id": dat[0],
            "name": dat[1],
            "section": dat[2],
            "subsection": dat[3],
            "link": dat[4],
            "ntype": dat[5],
            "tags": dat[6],
            "version": dat[7],
            "description": dat[8],
        }
        for dat in nodes_data
    ]
    cres = [
        {
            "id": dat[0],
            "name": dat[1],
            "description": dat[2],
            "external_id": dat[3],
            "tags": dat[4],
        }
        for dat in cre_data
    ]
    cre_links = [
        {"type": dat[0], "group": dat[1], "cre": dat[2]} for dat in cre_link_data
    ]

    cre_node_links = [
        {"type": dat[0], "cre": dat[1], "node": dat[2]} for dat in cre_node_link_data
    ]

    op.bulk_insert(cre_table, cres)
    op.bulk_insert(node_table, nodes)
    op.bulk_insert(cre_link_table, cre_links)
    op.bulk_insert(cre_node_link_table, cre_node_links)


def update_ids_to_uuid():
    config = op.get_context().config
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy."
    )
    connection = op.get_bind()

    nodes = connection.execute(text(f"Select id from node{temp_table_number}"))
    nodes_data = nodes.fetchall() if nodes else []

    cre = connection.execute(text(f"Select id from cre{temp_table_number}"))
    cre_data = cre.fetchall() if cre else []

    for id in nodes_data:
        node_uuid = generate_uuid()
        connection.execute(
            text(
                f"UPDATE  node{temp_table_number} set id='{node_uuid}' WHERE id={id[0]}"
            )
        )
        connection.execute(
            text(
                f"UPDATE cre_node_links{temp_table_number} set node='{node_uuid}' WHERE node={id[0]}"
            )
        )

    for id in cre_data:
        cre_uuid = generate_uuid()
        connection.execute(
            text(f"UPDATE cre{temp_table_number} set id='{cre_uuid}' WHERE id={id[0]}")
        )
        connection.execute(
            text(
                f"UPDATE cre_links{temp_table_number} set cre='{cre_uuid}' WHERE cre={id[0]}"
            )
        )
        connection.execute(
            text(
                f'UPDATE cre_links{temp_table_number} set "group"=\'{cre_uuid}\' WHERE "group"={id[0]}'
            )
        )
        connection.execute(
            text(
                f'UPDATE cre_node_links{temp_table_number} set "cre"=\'{cre_uuid}\' WHERE "cre"={id[0]}'
            )
        )


def downgrade_uuid_to_id():
    config = op.get_context().config
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy."
    )
    connection = op.get_bind()
    nodes = connection.execute(text("Select id from node"))
    nodes_data = nodes.fetchall() if nodes else []

    cre = connection.execute(text("Select id from cre"))
    cre_data = cre.fetchall() if cre else []

    node_id = 1
    for id in nodes_data:
        connection.execute(
            text(
                f"UPDATE node{temp_table_number} set id='{node_id}' WHERE id='{id[0]}'"
            )
        )
        connection.execute(
            text(
                f"UPDATE cre_node_links set node{temp_table_number}='{node_id}' WHERE node='{id[0]}'"
            )
        )
        node_id = node_id + 1

    cre_id = 1
    for id in cre_data:
        connection.execute(
            text(f"UPDATE cre{temp_table_number} set id='{cre_id}' WHERE id='{id[0]}'")
        )
        connection.execute(
            text(
                f"UPDATE cre_links{temp_table_number} set cre='{cre_id}' WHERE cre='{id[0]}'"
            )
        )
        connection.execute(
            text(
                f"UPDATE cre_links{temp_table_number} set \"group\"='{cre_id}' WHERE \"group\"='{id[0]}'"
            )
        )
        connection.execute(
            text(
                f"UPDATE cre_node_links{temp_table_number} set \"cre\"='{cre_id}' WHERE \"cre\"='{id[0]}'"
            )
        )
        cre_id = cre_id + 1


def create_tmp_tables(id_datatype):
    cre2 = op.create_table(
        f"cre{temp_table_number}",
        sa.Column("id", id_datatype, primary_key=True),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("tags", sa.String(), nullable=True),
    )
    node2 = op.create_table(
        f"node{temp_table_number}",
        sa.Column("id", id_datatype, primary_key=True),
        sa.Column("name", sa.String()),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("subsection", sa.String()),
        sa.Column("tags", sa.String()),
        sa.Column("version", sa.String()),
        sa.Column("description", sa.String()),
        sa.Column("ntype", sa.String()),
        sa.Column("link", sa.String()),
    )
    cre_links2 = op.create_table(
        f"cre_links{temp_table_number}",
        sa.Column("type", sa.String()),
        sa.Column(
            "group",
            id_datatype,
            sa.ForeignKey(
                f"cre{temp_table_number}.id", onupdate="CASCADE", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column(
            "cre",
            id_datatype,
            sa.ForeignKey(
                f"cre{temp_table_number}.id", onupdate="CASCADE", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
    )
    cre_node_links2 = op.create_table(
        f"cre_node_links{temp_table_number}",
        sa.Column("type", sa.String()),
        sa.Column(
            "cre",
            id_datatype,
            sa.ForeignKey(
                f"cre{temp_table_number}.id", onupdate="CASCADE", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column(
            "node",
            id_datatype,
            sa.ForeignKey(
                f"node{temp_table_number}.id", onupdate="CASCADE", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
    )
    return cre2, node2, cre_links2, cre_node_links2


def drop_old_tables():
    op.drop_table("cre_links")
    op.drop_table("cre_node_links")
    op.drop_table("cre")
    op.drop_table("node")


def cleanup():
    # op.drop_table("cre_links2")
    # op.drop_table("cre_node_links2")
    # op.drop_table("cre2")
    # op.drop_table("node2")
    pass


def rename_tables():
    op.rename_table(f"cre{temp_table_number}", "cre")
    op.rename_table(f"node{temp_table_number}", "node")
    op.rename_table(f"cre_links{temp_table_number}", "cre_links")
    op.rename_table(f"cre_node_links{temp_table_number}", "cre_node_links")


def add_constraints():
    with op.batch_alter_table("cre") as batch_op:
        batch_op.create_unique_constraint(
            columns=["name", "external_id"], constraint_name="unique_cre_fields"
        )

    with op.batch_alter_table("node") as batch_op:
        batch_op.create_unique_constraint(
            columns=[
                "name",
                "section",
                "subsection",
                "ntype",
                "description",
                "version",
            ],
            constraint_name="uq_node",
        )
    with op.batch_alter_table("cre_links") as batch_op:
        batch_op.create_unique_constraint(
            columns=["group", "cre"], constraint_name="uq_cre_link_pair"
        )
    with op.batch_alter_table("cre_node_links") as batch_op:
        batch_op.create_unique_constraint(
            columns=["cre", "node"],
            constraint_name="uq_cre_node_link_pair",
        )


# WARNING: The following recreates the entire DB, hence will be relatively slow for big databases
# Necessary since we are changing all primary and foreign keys
def upgrade():
    cre2, node2, cre_links2, cre_node_links2 = create_tmp_tables(sa.String())
    copy_tables(
        cre_table=cre2,
        node_table=node2,
        cre_link_table=cre_links2,
        cre_node_link_table=cre_node_links2,
    )
    update_ids_to_uuid()
    drop_old_tables()
    rename_tables()
    add_constraints()


def downgrade():
    cleanup()
    cre2, node2, cre_links2, cre_node_links2 = create_tmp_tables(sa.Integer())
    copy_tables(
        cre_table=cre2,
        node_table=node2,
        cre_link_table=cre_links2,
        cre_node_link_table=cre_node_links2,
    )
    downgrade_uuid_to_id()
    drop_old_tables()
    rename_tables()
    add_constraints()
