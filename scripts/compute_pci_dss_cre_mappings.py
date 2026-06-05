#!/usr/bin/env python3
"""
Compute PCI DSS v4 control → CRE mappings using Gemini embeddings + staged similarity.

Reads the public PCI DSS spreadsheet CSV, embeds each control, and resolves CRE links
using the same logic as application/utils/external_project_parsers/parsers/pci_dss.py.

Usage:
  python scripts/compute_pci_dss_cre_mappings.py \\
    --cache-file standards_cache.sqlite \\
    --output data/pci_dss_cre_mappings.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Repo root on sys.path when invoked as a script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from application.cmd.cre_main import db_connect  # noqa: E402
from application.defs import cre_defs as defs  # noqa: E402
from application.prompt_client import prompt_client  # noqa: E402
from application.utils.external_project_parsers.parsers.pci_dss import (  # noqa: E402
    PCI_BRIDGE_STANDARDS,
    PCI_DSS_CRE_SIMILARITY_THRESHOLDS,
    best_cre_via_bridge_standard,
    pci_control_embedding_text,
)

PCI_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "18weo-qbik_C7SdYq7FSP2OMgUmsWdWWI1eaXcAfMz8I/export?format=csv"
)

logger = logging.getLogger(__name__)


def _configure_llm_env() -> None:
    embed_model = os.environ.get("CRE_EMBED_MODEL")
    if not embed_model:
        vertex_embed = os.environ.get(
            "VERTEX_EMBED_CONTENT_MODEL", "gemini-embedding-001"
        )
        os.environ["CRE_EMBED_MODEL"] = f"gemini/{vertex_embed}"
    os.environ.setdefault("CRE_EMBED_EXPECTED_DIM", "3072")
    os.environ.setdefault("CRE_VALIDATE_EMBED_DIM_ON_INIT", "0")


def fetch_pci_rows(url: str = PCI_SHEET_CSV_URL) -> List[Dict[str, str]]:
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    rows = [row for row in reader if (row.get("PCI DSS ID") or "").strip()]
    if not rows:
        raise RuntimeError(f"no PCI rows found at {url}")
    return rows


def resolve_with_method(
    prompt: prompt_client.PromptHandler,
    cache,
    control_embedding: List[float],
) -> tuple[Optional[defs.CRE], str, Optional[float]]:
    for threshold in PCI_DSS_CRE_SIMILARITY_THRESHOLDS:
        match = prompt.get_id_of_most_similar_cre_paginated(
            control_embedding, similarity_threshold=threshold
        )
        if match and match[0]:
            cre = cache.get_cre_by_db_id(match[0])
            if cre:
                return cre, f"cre_similarity>={threshold}", float(match[1])

    for standard_name in PCI_BRIDGE_STANDARDS:
        cre = best_cre_via_bridge_standard(cache, control_embedding, standard_name)
        if cre:
            return cre, f"bridge:{standard_name}", None

    standard_id = prompt.get_id_of_most_similar_node(control_embedding)
    if standard_id:
        nodes = cache.get_nodes(db_id=standard_id)
        if nodes:
            linked_cres = cache.find_cres_of_node(nodes[0])
            if linked_cres:
                cre = cache.get_cre_by_db_id(linked_cres[0].id)
                if cre:
                    return cre, f"global_standard:{nodes[0].name}", None
    return None, "unlinked", None


def compute_mappings(
    cache,
    rows: List[Dict[str, str]],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    prompt = prompt_client.PromptHandler(cache)
    mappings: List[Dict[str, Any]] = []
    total = len(rows) if limit is None else min(limit, len(rows))

    for index, row in enumerate(rows[:total], start=1):
        section_id = str(row.get("PCI DSS ID", "")).strip()
        section = str(row.get("Defined Approach Requirements", "")).strip()
        description = str(
            row.get("Requirement Description", "") or row.get("Guidance", "")
        ).strip()
        control = defs.Standard(
            name="PCI DSS",
            sectionID=section_id,
            section=section,
            description=description,
            version="4",
        )
        if control.section.startswith(control.sectionID):
            control.section = control.section[len(control.sectionID) :].strip()

        embedding_text = pci_control_embedding_text(control)
        t0 = time.time()
        embedding = prompt.get_text_embeddings(embedding_text)
        cre, method, similarity = resolve_with_method(prompt, cache, embedding)
        elapsed = time.time() - t0

        entry: Dict[str, Any] = {
            "pci_dss_id": section_id,
            "section": control.section,
            "cre_id": cre.id if cre else None,
            "cre_name": cre.name if cre else None,
            "method": method,
            "similarity": similarity,
            "elapsed_seconds": round(elapsed, 2),
        }
        mappings.append(entry)
        status = cre.id if cre else "UNLINKED"
        logger.info("[%s/%s] %s -> %s (%s)", index, total, section_id, status, method)

    return mappings


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute PCI DSS → CRE mappings")
    parser.add_argument(
        "--cache-file",
        default=os.environ.get(
            "CRE_CACHE_FILE", os.path.join(_REPO_ROOT, "standards_cache.sqlite")
        ),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(_REPO_ROOT, "data", "pci_dss_cre_mappings.json"),
    )
    parser.add_argument("--sheet-url", default=PCI_SHEET_CSV_URL)
    parser.add_argument(
        "--limit", type=int, default=None, help="process only first N controls"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    _configure_llm_env()

    rows = fetch_pci_rows(args.sheet_url)
    logger.info("loaded %s PCI DSS controls from spreadsheet", len(rows))

    cache = db_connect(path=args.cache_file)
    mappings = compute_mappings(cache, rows, limit=args.limit)

    linked = [m for m in mappings if m["cre_id"]]
    unlinked = [m for m in mappings if not m["cre_id"]]
    summary = {
        "total": len(mappings),
        "linked": len(linked),
        "unlinked": len(unlinked),
        "unlinked_ids": [m["pci_dss_id"] for m in unlinked],
        "thresholds": list(PCI_DSS_CRE_SIMILARITY_THRESHOLDS),
        "bridge_standards": list(PCI_BRIDGE_STANDARDS),
        "embed_model": os.environ.get("CRE_EMBED_MODEL"),
    }
    payload = {"summary": summary, "mappings": mappings}

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    logger.info(
        "wrote %s mappings to %s (%s linked, %s unlinked)",
        len(mappings),
        args.output,
        len(linked),
        len(unlinked),
    )
    if unlinked:
        logger.error("unlinked controls: %s", ", ".join(summary["unlinked_ids"][:10]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
