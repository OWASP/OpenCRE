import os
import sys

# Ensure application matches the import path
sys.path.append(os.getcwd())

from application.database import db
from application.defs import cre_defs as defs
from application.cmd.cre_main import db_connect
from application.config import CMDConfig
from application import create_app


def seed_attacks():
    # Database path
    db_path = os.path.abspath("standards_cache.sqlite")
    print(f"Connecting to DB at {db_path}...")

    # Setup context
    conf = CMDConfig(db_uri=db_path)
    app = create_app(conf=conf)
    app_context = app.app_context()
    app_context.push()

    collection = db.Node_collection()

    # Define Attacks
    attacks = [
        defs.Attack(
            name="Path Traversal",
            hyperlink="https://owasp.org/www-community/attacks/Path_Traversal",
            tags=["OWASP", "Attack"],
        ),
        defs.Attack(
            name="SQL Injection",
            hyperlink="https://owasp.org/www-community/attacks/SQL_Injection",
            tags=["OWASP", "Attack"],
        ),
    ]

    # Register
    print("Seeding attacks...")
    for attack in attacks:
        # Idempotency Check
        existing = collection.get_nodes(name=attack.name)
        # Filter for existing attacks with same hyperlink to be precise
        if existing and any(n.hyperlink == attack.hyperlink for n in existing):
            print(f"  Skipping existing: {attack.name}")
            continue

        db_node = collection.add_node(attack)
        print(f"  Added: {attack.name} (ID: {db_node.id})")

    # Verification
    print("\nVerifying...")
    nodes = collection.get_nodes(name="SQL Injection", ntype=defs.Attack.__name__)
    found = False
    for n in nodes:
        if n.doctype == defs.Credoctypes.Attack:
            print(f"✅ Found Attack: {n.name} ({n.hyperlink}) - Type: {n.doctype}")
            found = True

    if not found:
        print("❌ Verification Failed: SQL Injection Attack node not found!")
        sys.exit(1)


if __name__ == "__main__":
    seed_attacks()
