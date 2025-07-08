from application.defs import cre_defs as defs
from application.cmd import cre_main as main
from application.database import db
from application import create_app, sqla  # ✅ use sqla like in db_test.py


def generate_synthetic_cre_standard_graph(n_cres=200, n_standards=10):
    collection = db.Node_collection().with_graph()

    standards = [
        defs.Standard(
            name=f"Standard_{i}",
            section=f"Section_{i}",
        )
        for i in range(n_standards)
    ]

    for standard in standards:
        main.register_node(standard, collection)

    for i in range(n_cres):
        linked_standards = [
            defs.Link(document=standards[i % n_standards],
                      ltype=defs.LinkTypes.LinkedTo)
        ]
        cre = defs.CRE(
            id=f"{i // 1000:03}-{i % 1000:03}",
            name=f"CRE_Name_{i}",
            description="Synthetic CRE for benchmarking",
            links=linked_standards,
        )
        main.register_cre(cre, collection)

    print(f"Generated {n_cres} CREs and {n_standards} Standards.")
    return collection


if __name__ == "__main__":
    print("Starting synthetic graph generation...")

    app = create_app(mode="test")
    with app.app_context():
        sqla.create_all()
        collection = generate_synthetic_cre_standard_graph(
            n_cres=200, n_standards=10)

        # Save collection to SQLite cache
        # <-- Confirm if this method exists for Node_collection or find the right save method
        # collection.save()

        # Now populate Neo4j from SQLite cache
        main.populate_neo4j_db(
            "/path/to/standards_cache.sqlite")  # Use correct path

    print("Finished synthetic graph generation.")
