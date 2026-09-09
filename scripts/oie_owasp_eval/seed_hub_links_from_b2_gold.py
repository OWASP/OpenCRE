#!/usr/bin/env python3
"""Seed hub Nodes+Links from B2 gold JSON (production map-once helper ONLY).

WARNING: Do **not** use this before a B2 accuracy run. Seeding gold then
scoring against the same gold is circular (proves Link-prior, not transfer
from related standards).

For eval (path B): leave target families unmapped; Module C must use organic
hub Links (Top10 2021, CCM, ASVS, LLM/AIX, …) + edition remap / control-name.

This script is for simulating a human map-once into the hub after review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "scripts" / "oie_owasp_eval" / "fixtures" / "b2_gold"
FIXTURE_DIR = ROOT / "application" / "tests" / "fixtures" / "owasp_mappings"

# (gold path candidates, Node.name, version string)
SEED_SPECS: List[Tuple[List[Path], str, str]] = [
    (
        [
            GOLD_DIR / "owasp_kubernetes_top10_2022_pr927.json",
            FIXTURE_DIR / "owasp_kubernetes_top10_2022.json",
            ROOT
            / "application"
            / "utils"
            / "external_project_parsers"
            / "data"
            / "owasp_kubernetes_top10_2022.json",
        ],
        "OWASP Kubernetes Top Ten 2022",
        "2022",
    ),
    (
        [
            GOLD_DIR / "owasp_kubernetes_top10_2025.json",
            FIXTURE_DIR / "owasp_kubernetes_top10_2025.json",
        ],
        "OWASP Kubernetes Top Ten 2025",
        "2025",
    ),
    (
        [
            GOLD_DIR / "owasp_top10_2025.json",
            FIXTURE_DIR / "owasp_top10_2025.json",
        ],
        "OWASP Top 10 2025",
        "2025",
    ),
    (
        [
            GOLD_DIR / "owasp_api_top10_2023.json",
            FIXTURE_DIR / "owasp_api_top10_2023.json",
        ],
        "OWASP API Security Top 10 2023",
        "2023",
    ),
]


def _load_dotenv() -> None:
    for env_path in (ROOT / ".env", ROOT / "tmp" / "oie.env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if env_path.name == "oie.env" and (
                k.startswith("CRE_LIBRARIAN_") or k.startswith("DEV_DATABASE")
            ):
                os.environ[k.strip()] = v.strip()
            else:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _first_existing(paths: Sequence[Path]) -> Optional[Path]:
    for p in paths:
        if p.is_file():
            return p
    return None


def _load_rows(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected JSON list")
    return [r for r in data if isinstance(r, dict)]


def seed_standard(
    database: Any,
    *,
    name: str,
    version: str,
    rows: Sequence[Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, int]:
    from application.database.db import CRE, Links
    from application.defs import cre_defs

    stats = {
        "sections": 0,
        "nodes_upserted": 0,
        "links_added": 0,
        "links_existed": 0,
        "missing_cres": 0,
        "empty_sections": 0,
    }
    for row in rows:
        sid = str(row.get("section_id") or "").strip()
        title = str(row.get("section") or sid).strip()
        href = str(row.get("hyperlink") or "").strip()
        cre_ids = [str(c) for c in (row.get("cre_ids") or []) if c]
        if not sid:
            continue
        stats["sections"] += 1
        if not cre_ids:
            stats["empty_sections"] += 1
            continue

        if dry_run:
            for ext in cre_ids:
                cre = (
                    database.session.query(CRE)
                    .filter(CRE.external_id == ext)
                    .first()
                )
                if cre is None:
                    stats["missing_cres"] += 1
                else:
                    stats["links_added"] += 1
            stats["nodes_upserted"] += 1
            continue

        std = cre_defs.Standard(
            name=name,
            section=title,
            sectionID=sid,
            subsection="",
            version=version,
            hyperlink=href,
        )
        dbnode = database.add_node(std)
        if dbnode is None:
            continue
        stats["nodes_upserted"] += 1

        for ext in cre_ids:
            cre = (
                database.session.query(CRE).filter(CRE.external_id == ext).first()
            )
            if cre is None:
                stats["missing_cres"] += 1
                continue
            existed = (
                database.session.query(Links)
                .filter(Links.cre == cre.id, Links.node == dbnode.id)
                .first()
            )
            database.add_link(cre, dbnode, cre_defs.LinkTypes.LinkedTo)
            if existed:
                stats["links_existed"] += 1
            else:
                stats["links_added"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cache-file", default="")
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    _load_dotenv()
    cache = (
        args.cache_file
        or os.environ.get("DEV_DATABASE_URL")
        or os.environ.get("CRE_CACHE_FILE")
        or ""
    )
    if not cache:
        print("DEV_DATABASE_URL / --cache-file required", file=sys.stderr)
        return 2

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database import db as db_module

    db_connect(cache)
    database = db_module.Node_collection()

    report: Dict[str, Any] = {"dry_run": args.dry_run, "standards": []}
    for paths, name, version in SEED_SPECS:
        path = _first_existing(paths)
        if path is None:
            report["standards"].append(
                {"name": name, "version": version, "error": "gold file missing"}
            )
            continue
        rows = _load_rows(path)
        stats = seed_standard(
            database, name=name, version=version, rows=rows, dry_run=args.dry_run
        )
        report["standards"].append(
            {
                "name": name,
                "version": version,
                "source": str(path),
                **stats,
            }
        )

    if not args.dry_run:
        sqla.session.commit()

    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
