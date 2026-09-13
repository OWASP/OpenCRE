#!/usr/bin/env python3
"""Tag standard Node rows with OIE section/class/family metadata.

Writes ``Node.metadata_json["oie"]`` (DB column ``document_metadata``) so
Module C.0.4 can resolve Section-ID → class/family from the hub instead of
hardcoded Python maps.

Bootstrap seed lives in ``scripts/oie_taxonomy_bootstrap.py`` (migration only).
After tagging, librarian runtime reads Node metadata only.

Usage:
  PYTHONPATH=. python scripts/oie_tag_standard_sections.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre

  PYTHONPATH=. python scripts/oie_tag_standard_sections.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Allow importing sibling bootstrap module when run as a script.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from oie_taxonomy_bootstrap import (  # noqa: E402
    FAMILY_TO_TRANSFER_SEED,
    OIE_META_VERSION,
    RELATED_CLASSES_SEED,
    SECTION_ID_SEED,
    STANDARD_HINTS_BY_FAMILY,
    normalize_section_id,
    phrases_for_class,
)

_CATALOG_ID = re.compile(
    r"(?<![A-Za-z0-9])(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS\d{1,2})(?![A-Za-z0-9])",
    re.I,
)


def _extract_section_id(node: Any) -> Optional[str]:
    raw = getattr(node, "section_id", None) or ""
    sid = normalize_section_id(str(raw))
    if sid in SECTION_ID_SEED:
        return sid
    # LLM01:2025 style
    if ":" in str(raw):
        sid = normalize_section_id(str(raw).split(":")[0])
        if sid in SECTION_ID_SEED:
            return sid
    for field in (getattr(node, "section", None), getattr(node, "name", None)):
        if not field:
            continue
        m = _CATALOG_ID.search(str(field))
        if m:
            sid = m.group(1).upper()
            if sid in SECTION_ID_SEED:
                return sid
    return None


def _catalog_standard_family(sid: str) -> str:
    """Default problem family for Standard: line when only the catalog is known."""
    if sid.startswith("API"):
        return "api"
    if sid.startswith("LLM") or sid.startswith("AISVS"):
        return "ai"
    if re.match(r"^K\d", sid):
        return "cloud"
    if re.match(r"^A\d", sid):
        return "appsec"
    return ""


def build_node_oie(node: Any) -> Optional[Dict[str, Any]]:
    sid = _extract_section_id(node)
    if not sid:
        return None
    class_id, family = SECTION_ID_SEED[sid]
    transfer = FAMILY_TO_TRANSFER_SEED.get(family, "")
    related = list(RELATED_CLASSES_SEED.get(class_id, ()))
    phrases = phrases_for_class(class_id)
    title = (getattr(node, "section", None) or "").strip()
    if title and title.lower() not in {p.lower() for p in phrases}:
        phrases = [title] + phrases
    standard_family = _catalog_standard_family(sid) or family
    hints = list(STANDARD_HINTS_BY_FAMILY.get(standard_family, ()))
    return {
        "version": OIE_META_VERSION,
        "section_id": sid,
        "class_id": class_id,
        "family": family,
        "standard_family": standard_family,
        "related_classes": related,
        "transfer": transfer,
        "phrases": phrases[:24],
        "standard_hints": hints,
        "section_title": title or None,
    }


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
    from application.database.db import Node

    db_connect(args.cache_file)

    updated = 0
    scanned = 0
    samples: List[Dict[str, Any]] = []
    nodes = sqla.session.query(Node).all()
    for node in nodes:
        scanned += 1
        oie = build_node_oie(node)
        if oie is None:
            continue
        meta = dict(node.metadata_json or {})
        prev = meta.get("oie")
        meta["oie"] = oie
        if prev == oie:
            continue
        updated += 1
        if len(samples) < 8:
            samples.append(
                {
                    "name": node.name,
                    "section_id": node.section_id,
                    "section": node.section,
                    "oie": oie,
                }
            )
        if not args.dry_run:
            node.metadata_json = meta

    if not args.dry_run:
        sqla.session.commit()

    report = {
        "dry_run": args.dry_run,
        "nodes_scanned": scanned,
        "updated": updated,
        "samples": samples,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
