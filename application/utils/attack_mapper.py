import re
import logging
from typing import List, Optional
from application.database import db
from application.defs import cre_defs as defs

logger = logging.getLogger(__name__)


def extract_cwe_ids(text: str) -> List[str]:
    """Finds all occurrences of 'CWE-<numbers>' in the text."""
    if not text:
        return []
    # Match CWE-123, CWE: 123, etc. strictly CWE-\d+ for now as per plan
    matches = re.findall(r"CWE-(\d+)", text, re.IGNORECASE)
    return [f"CWE-{m}" for m in matches]


def link_attack_to_cre_by_cwe(
    attack: defs.Attack, collection: db.Node_collection
) -> List[str]:
    """
    Links the Attack node to CREs that are already linked to the CWEs mentioned in the Attack's description.
    Returns a list of linked CRE names/IDs.
    """
    linked_cres = []
    cwe_ids = extract_cwe_ids(attack.description)

    if not cwe_ids:
        return []

    for cwe_name in set(cwe_ids):
        # 1. Find the CWE Node
        # CWEs are Standards.
        cwe_nodes = collection.get_nodes(name=cwe_name)
        if not cwe_nodes:
            continue

        cwe_node = cwe_nodes[0]

        # 2. Find CREs linked to this CWE
        # This requires querying the Links table.
        # Node_collection doesn't expose get_links_for_node directly?
        # We can access the session or use get_CREs with include_only?
        # get_CREs doesn't filter by "linked to node X".
        # We will iterate manually or use db.session if available.
        # collection.session is likely the db.session

        links = (
            collection.session.query(db.Links)
            .filter(db.Links.node == cwe_node.id)
            .all()
        )

        for link in links:
            cre_id = link.cre

            # Use get_CREs by internal_id first
            cre_list = collection.get_CREs(internal_id=cre_id)

            if not cre_list:
                # Fallback: Maybe the link stores external_id?
                cre_list = collection.get_CREs(external_id=cre_id)

            if cre_list:
                cre = cre_list[0]
                # HACK: Retrieve the underlying DB UUID to ensure Links table uses PK
                # get_CREs returns defs.CRE where .id is usually .external_id
                # But Links table FK points to .id (UUID)
                db_cre = (
                    collection.session.query(db.CRE)
                    .filter(db.CRE.external_id == cre.id)
                    .first()
                )
                if db_cre:
                    if db_cre:
                        cre.id = db_cre.id

                collection.add_link(cre=cre, node=attack, ltype=defs.LinkTypes.Related)
                linked_cres.append(f"{cre.name} (via {cwe_name})")

    return linked_cres
