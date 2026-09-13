#!/usr/bin/env python3
"""Tag CRE rows with verbose OIE classification metadata.

Writes ``CRE.metadata_json["oie"]`` (DB column ``document_metadata``): families,
classes, domains, standards, signals, transfers. Inference uses linked standard
names + CRE text via bootstrap helpers in ``scripts/oie_taxonomy_bootstrap.py``
(migration seed only — not imported by librarian runtime).

Also recommend tagging standard Nodes first::

  PYTHONPATH=. python scripts/oie_tag_standard_sections.py --cache-file ...

Usage:
  PYTHONPATH=. python scripts/oie_tag_cre_families.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre

  PYTHONPATH=. python scripts/oie_tag_cre_families.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from oie_taxonomy_bootstrap import tag_cre_from_names  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get(
            "DEV_DATABASE_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import CRE, Links, Node

    db_connect(args.cache_file)

    names_by_cre: Dict[str, List[str]] = defaultdict(list)
    node_oie_by_cre: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    rows = (
        sqla.session.query(
            CRE.id, CRE.external_id, CRE.name, Node.name, Node.metadata_json
        )
        .join(Links, Links.cre == CRE.id)
        .join(Node, Node.id == Links.node)
        .all()
    )
    for cre_id, _ext, cre_name, node_name, node_meta in rows:
        if node_name:
            names_by_cre[cre_id].append(str(node_name))
        if cre_name:
            names_by_cre[cre_id].append(str(cre_name))
        if isinstance(node_meta, dict):
            block = node_meta.get("oie")
            if isinstance(block, dict):
                node_oie_by_cre[cre_id].append(block)

    updated = 0
    samples: List[Dict[str, Any]] = []
    cres = sqla.session.query(CRE).all()
    for cre in cres:
        linked = list(names_by_cre.get(cre.id, []))
        oie = tag_cre_from_names(
            cre_name=cre.name or "",
            description=cre.description or "",
            linked_names=linked,
        )
        # Prefer transfer/class signals already on linked standard Nodes.
        for block in node_oie_by_cre.get(cre.id, []):
            fam = block.get("family")
            cid = block.get("class_id")
            transfer = block.get("transfer")
            families = list(oie.get("families") or [])
            classes = list(oie.get("classes") or [])
            transfers = list(oie.get("transfers") or [])
            signals = list(oie.get("signals") or [])
            if fam and fam not in families:
                families.append(str(fam))
            if cid and cid not in classes:
                classes.append(str(cid))
            if transfer and transfer not in transfers:
                transfers.append(str(transfer))
                if transfer not in signals:
                    signals.append(str(transfer))
            oie["families"] = sorted(families)
            oie["classes"] = sorted(classes)
            oie["transfers"] = sorted(transfers)
            oie["signals"] = sorted(signals)[:24]

        meta = dict(cre.metadata_json or {})
        prev = meta.get("oie")
        meta["oie"] = oie
        # Legacy mirrors for older prior builders / ad-hoc queries.
        meta["oie_families"] = list(oie.get("families") or [])
        meta["oie_classes"] = list(oie.get("classes") or [])
        if prev == oie and meta.get("oie_families") == oie.get("families"):
            continue
        updated += 1
        if len(samples) < 8:
            samples.append(
                {
                    "external_id": cre.external_id,
                    "name": cre.name,
                    "oie": oie,
                }
            )
        if not args.dry_run:
            cre.metadata_json = meta

    if not args.dry_run:
        sqla.session.commit()

    report = {
        "dry_run": args.dry_run,
        "cre_total": len(cres),
        "updated": updated,
        "samples": samples,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
