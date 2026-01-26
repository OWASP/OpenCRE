import os
import sys
import logging

# Ensure application matches the import path
sys.path.append(os.getcwd())

from application.database import db
from application.defs import cre_defs as defs
from application.cmd.cre_main import db_connect
from application.config import CMDConfig
from application import create_app

# Import our new utility
from application.utils.attack_mapper import link_attack_to_cre_by_cwe

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def seed_cwe_structure(collection):
    """Mocks the existing CWE->CRE structure if it doesn't exist."""
    print("\n--- Seeding Mock CWE Structure ---")

    # 1. Create a CRE "Input Validation" (Mock)
    cre = defs.CRE(
        name="Input Validation (Mock)",
        id="999-999",
        description="Mitigation for input attacks",
    )
    db_cre = collection.add_cre(cre)
    cre.id = db_cre.id  # Use DB PK (UUID) for linking
    print(f"  Added/Found CRE: {cre.name}")

    # 2. Create CWE-22 (Standard)
    cwe = defs.Standard(
        name="CWE-22",
        section="Path Traversal",
        hyperlink="https://cwe.mitre.org/data/definitions/22.html",
    )
    db_cwe = collection.add_node(cwe)
    cwe.id = db_cwe.id  # Use DB PK (UUID) for linking
    print(f"  Added/Found CWE: {cwe.name}")

    # 3. Link CWE -> CRE
    # add_link(cre, node)
    collection.add_link(cre=cre, node=cwe, ltype=defs.LinkTypes.Related)
    print(f"  Linked CWE-22 -> Input Validation")


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

    # Step 0: Ensure CWE infrastructure exists
    seed_cwe_structure(collection)

    print("\n--- Seeding Attacks ---")
    # Define Attacks with Descriptions containing CWEs
    attacks = [
        defs.Attack(
            name="Path Traversal",
            hyperlink="https://owasp.org/www-community/attacks/Path_Traversal",
            tags=["OWASP", "Attack"],
            description="The Path Traversal attack technique allows... Related CWEs: CWE-22.",
        ),
        defs.Attack(
            name="SQL Injection",
            hyperlink="https://owasp.org/www-community/attacks/SQL_Injection",
            tags=["OWASP", "Attack"],
            description="SQL Injection attacks... Related CWEs: CWE-89.",
            # Note: CWE-89 is not mocked above, so this should NOT link, testing negative case/robustness
        ),
    ]

    # Register Attacks
    for attack in attacks:
        # Idempotency Check
        existing = collection.get_nodes(name=attack.name, ntype=defs.Attack.__name__)
        if existing:
            # Update description to ensure we test parsing
            if existing[0].description != attack.description:
                print(f"  Updating description for {attack.name}")
                # We can use add_node to update
                collection.add_node(attack)
            else:
                print(f"  Skipping existing: {attack.name}")
        else:
            db_node = collection.add_node(attack)
            print(f"  Added: {attack.name}")

        # Ensure attack.id is the DB UUID for linking
        db_node_obj = (
            collection.session.query(db.Node)
            .filter(db.Node.name == attack.name)
            .first()
        )
        if db_node_obj:
            attack.id = db_node_obj.id

        # --- PHASE 2: AUTO LINKING ---
        print(f"  Running Auto-Linking for {attack.name}...")
        linked_cres = link_attack_to_cre_by_cwe(attack, collection)
        if linked_cres:
            print(f"  ✅ Linked to: {linked_cres}")
        else:
            print(f"  (No links created)")

    # Verification
    print("\n--- Final Verification ---")
    # Verify Path Traversal is linked to "Input Validation (Mock)"
    # We can check by fetching the CRE and listing its links

    cre_nodes = collection.get_CREs(name="Input Validation (Mock)")
    if not cre_nodes:
        print("❌ Mock CRE not found during verification!")
        sys.exit(1)

    mock_cre = cre_nodes[0]
    # Verify it links to "Path Traversal"
    found_link = False
    for link in mock_cre.links:
        # link.document is the linked node
        # We need to check if it's our attack
        if (
            link.document.name == "Path Traversal"
            and link.document.doctype == defs.Credoctypes.Attack
        ):
            found_link = True
            print(
                f"✅ Verified Link: CRE '{mock_cre.name}' <--> Attack '{link.document.name}'"
            )
            break

    if not found_link:
        print("❌ Verification Failed: Link between CRE and Attack NOT found.")
        sys.exit(1)


if __name__ == "__main__":
    seed_attacks()
