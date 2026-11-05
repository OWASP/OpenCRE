#!/usr/bin/env python3
"""
Verify that primary gap_analysis_results rows in Postgres match Neo4j for every
directed pair among GA-eligible standards (same matrix as /rest/v1/ga_standards).

Agreement rule (per pair):
  - Postgres primary row is "material" (non-empty JSON ``result``) iff
    ``NEO_DB.gap_analysis(A, B)`` returns at least one formatted path.

Also fails if any primary row exists with an empty ``{"result":{}}`` placeholder.

Environment:
  CRE_CACHE_FILE or PROD_DATABASE_URL — SQL DB URL (Postgres or SQLite)
  NEO4J_URL — Bolt URL for Neo4j

Usage:
  export CRE_CACHE_FILE=postgresql://cre:password@127.0.0.1:5432/cre
  export NEO4J_URL=bolt://neo4j:password@127.0.0.1:7687
  ./scripts/verify_ga_postgres_neo_parity.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_REPO_ROOT, ".venv", "bin", "python3")


def _maybe_reexec_with_repo_venv() -> None:
    if not os.path.isfile(_VENV_PY):
        return
    if os.path.abspath(sys.executable) == os.path.abspath(_VENV_PY):
        return
    env = os.environ.copy()
    env["PYTHONPATH"] = _REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    os.execve(_VENV_PY, [_VENV_PY, os.path.abspath(__file__), *sys.argv[1:]], env)


def main() -> int:
    _maybe_reexec_with_repo_venv()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-pairs",
        type=int,
        default=0,
        help="If >0, only check the first N pairs (debug)",
    )
    p.add_argument(
        "--output-json",
        default="",
        help="Write a JSON report to this path",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    db_url = os.environ.get("CRE_CACHE_FILE") or os.environ.get("PROD_DATABASE_URL")
    if not db_url:
        print(
            "Set CRE_CACHE_FILE or PROD_DATABASE_URL to your SQL database URL",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("NEO4J_URL", "bolt://neo4j:password@127.0.0.1:7687")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from neomodel import config

    config.DATABASE_URL = os.environ["NEO4J_URL"]

    from application.cmd import cre_main
    from application.database.db import NEO_DB, GapAnalysisResults
    from application.utils.gap_analysis import (
        make_resources_key,
        primary_gap_analysis_payload_is_material,
    )
    from application.utils.ga_parity import (
        count_empty_primary_gap_rows,
        directed_eligible_pairs,
        ga_matrix_standard_names,
        pg_neo_material_agree,
    )

    collection = cre_main.db_connect(db_url)
    standards = ga_matrix_standard_names(collection)
    pairs = directed_eligible_pairs(standards)
    if args.max_pairs > 0:
        pairs = pairs[: args.max_pairs]

    empty_primary = count_empty_primary_gap_rows(collection.session, GapAnalysisResults)
    if empty_primary:
        logging.error(
            "Found %s primary gap_analysis rows with empty/non-material result",
            empty_primary,
        )

    mismatches: list[dict[str, object]] = []
    neo = NEO_DB.instance()

    for i, (sa, sb) in enumerate(pairs):
        if i and i % 50 == 0:
            logging.info("checked %s/%s pairs", i, len(pairs))
        key = make_resources_key([sa, sb])
        row = (
            collection.session.query(GapAnalysisResults)
            .filter(GapAnalysisResults.cache_key == key)
            .first()
        )
        payload = str(row.ga_object) if row else ""
        pg_mat = primary_gap_analysis_payload_is_material(payload)

        parsed_base, parsed_paths = neo.gap_analysis(sa, sb)
        neo_n = len(parsed_paths)
        if not pg_neo_material_agree(pg_mat, neo_n):
            mismatches.append(
                {
                    "pair": f"{sa}->{sb}",
                    "cache_key": key,
                    "postgres_material": pg_mat,
                    "neo_formatted_paths": neo_n,
                    "neo_base_nodes": len(parsed_base),
                }
            )

    report = {
        "db_url_host": db_url.split("@")[-1] if "@" in db_url else db_url,
        "ga_matrix_standards": len(standards),
        "directed_pairs_checked": len(pairs),
        "empty_primary_placeholder_rows": empty_primary,
        "mismatch_count": len(mismatches),
        "mismatches_sample": mismatches[:40],
    }

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logging.info("Wrote %s", args.output_json)

    print(json.dumps(report, indent=2))

    if empty_primary or mismatches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
