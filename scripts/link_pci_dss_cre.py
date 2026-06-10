#!/usr/bin/env python3
"""
Link existing PCI DSS nodes to CRE via embedding similarity.

Use when PCI controls were imported with embeddings but without cre_node_links
(e.g. import ran with CRE_NO_GEN_EMBEDDINGS or linking failed). Mirrors the
linking logic in pci_dss.PciDss.__parse without re-fetching the spreadsheet.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("CRE_CACHE_FILE")
        or os.environ.get("PROD_DATABASE_URL")
        or "postgresql://cre:password@127.0.0.1:5432/cre",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report link candidates without writing",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger = logging.getLogger(__name__)

    from application.cmd import cre_main
    from application.database import db
    from application.defs import cre_defs as defs
    from application.prompt_client import prompt_client

    collection = cre_main.db_connect(args.cache_file)
    ph = prompt_client.PromptHandler(database=collection)

    pci_rows = (
        collection.session.query(db.Node)
        .filter(db.Node.name == "PCI DSS")
        .order_by(db.Node.section_id)
        .all()
    )
    if not pci_rows:
        logger.error("No PCI DSS nodes found in database")
        return 1

    pci_ids = [n.id for n in pci_rows if n.id]
    linked_before = (
        collection.session.query(db.Links).filter(db.Links.node.in_(pci_ids)).count()
        if pci_ids
        else 0
    )
    logger.info(
        "PCI DSS nodes=%s existing cre_node_links=%s",
        len(pci_rows),
        linked_before,
    )

    created = 0
    skipped_linked = 0
    skipped_no_match = 0

    for db_node in pci_rows:
        existing = (
            collection.session.query(db.Links)
            .filter(db.Links.node == db_node.id)
            .first()
        )
        if existing:
            skipped_linked += 1
            continue

        emb_row = (
            collection.session.query(db.Embeddings)
            .filter(db.Embeddings.node_id == db_node.id)
            .first()
        )
        if not emb_row or not emb_row.embeddings:
            logger.warning("No embedding for PCI node %s; skipping", db_node.section_id)
            skipped_no_match += 1
            continue

        control_embeddings = [float(e) for e in emb_row.embeddings.split(",")]
        cre_id = ph.get_id_of_most_similar_cre(control_embeddings)
        if not cre_id:
            standard_id = ph.get_id_of_most_similar_node(control_embeddings)
            if standard_id:
                dbstandard = collection.get_nodes(db_id=standard_id)
                if dbstandard:
                    cres = collection.find_cres_of_node(dbstandard[0])
                    if cres:
                        cre_row_candidate = (
                            collection.session.query(db.CRE)
                            .filter(db.CRE.external_id == cres[0].id)
                            .first()
                        )
                        if cre_row_candidate:
                            cre_id = cre_row_candidate.id
        if not cre_id:
            logger.info(
                "No CRE match for PCI %s (%s)",
                db_node.section_id or "",
                (db_node.section or "")[:60],
            )
            skipped_no_match += 1
            continue

        cre_row = collection.session.query(db.CRE).filter(db.CRE.id == cre_id).first()
        if not cre_row:
            skipped_no_match += 1
            continue

        if args.dry_run:
            logger.info(
                "Would link PCI %s -> CRE %s",
                db_node.section_id or "",
                cre_row.name,
            )
            created += 1
            continue

        collection.add_link(
            cre=cre_row,
            node=db_node,
            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
        )
        created += 1
        if created % 50 == 0:
            logger.info("Linked %s PCI controls so far", created)

    linked_after = (
        collection.session.query(db.Links).filter(db.Links.node.in_(pci_ids)).count()
        if pci_ids
        else 0
    )
    logger.info(
        "Done: new_links=%s skipped_already_linked=%s skipped_no_match=%s "
        "cre_node_links before=%s after=%s dry_run=%s",
        created,
        skipped_linked,
        skipped_no_match,
        linked_before,
        linked_after,
        args.dry_run,
    )
    return 0 if created > 0 or linked_after > linked_before else 1


if __name__ == "__main__":
    raise SystemExit(main())
