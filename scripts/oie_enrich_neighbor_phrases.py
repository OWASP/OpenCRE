#!/usr/bin/env python3
"""Enrich CCM / ASVS / Top10 Node ``oie.phrases`` for K8s/API title matching.

Does **not** write CRE Links for K8s/API (path B). Only adds alias phrases so
neighbor title/topic transfer can match wording like "RBAC", "network
segmentation", "object level authorization" onto related hub sections.

Usage:
  set -a && source tmp/oie.env && set +a
  PYTHONPATH=. python scripts/oie_enrich_neighbor_phrases.py
  PYTHONPATH=. python scripts/oie_enrich_neighbor_phrases.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]

# (Node.name regex, list of (section-title regex, phrases to add))
_ENRICHMENTS: List[Tuple[re.Pattern[str], List[Tuple[re.Pattern[str], List[str]]]]] = [
    (
        re.compile(r"cloud\s*controls\s*matrix", re.I),
        [
            (
                re.compile(r"identity|access|iam", re.I),
                [
                    "overly permissive authorization",
                    "overly permissive rbac",
                    "broken authentication",
                    "broken object level authorization",
                    "rbac",
                    "cluster access control",
                ],
            ),
            (
                re.compile(r"segment|segregat|network|ivs-0[689]", re.I),
                [
                    "missing network segmentation controls",
                    "network segmentation",
                    "cluster to cloud lateral movement",
                    "network policy",
                ],
            ),
            (
                re.compile(r"log|monitor", re.I),
                [
                    "inadequate logging and monitoring",
                    "logging and monitoring",
                    "audit logging",
                ],
            ),
            (
                re.compile(r"crypt|key|cek|secret", re.I),
                [
                    "secrets management failures",
                    "secrets management",
                    "static secrets",
                ],
            ),
            (
                re.compile(r"hardening|os|ivs-04|config|change", re.I),
                [
                    "insecure workload configurations",
                    "configuration hardening",
                    "misconfigured cluster components",
                ],
            ),
            (
                re.compile(r"vulnerab|threat|tvm", re.I),
                [
                    "outdated and vulnerable kubernetes components",
                    "vulnerable cluster components",
                    "supply chain vulnerabilities",
                ],
            ),
            (
                re.compile(r"infrastructure|virtualization|ivs", re.I),
                [
                    "overly exposed kubernetes components",
                    "cluster level policy enforcement",
                    "workload security",
                ],
            ),
        ],
    ),
    (
        re.compile(r"^ASVS$", re.I),
        [
            (
                re.compile(r"access|authoriz|v4", re.I),
                [
                    "broken object level authorization",
                    "broken function level authorization",
                    "broken object property level authorization",
                    "technical application access control",
                ],
            ),
            (
                re.compile(r"authenticat|session|v2|v3", re.I),
                [
                    "broken authentication",
                    "session management",
                    "secure user management",
                ],
            ),
            (
                re.compile(r"ssrf|ssrf|request", re.I),
                ["server side request forgery", "ssrf protection"],
            ),
            (
                re.compile(r"config|v14|v12", re.I),
                ["security misconfiguration", "configuration"],
            ),
            (
                re.compile(r"api|graphql|v13", re.I),
                [
                    "unsafe consumption of apis",
                    "unrestricted access to sensitive business flows",
                    "unrestricted resource consumption",
                ],
            ),
        ],
    ),
    (
        re.compile(r"owasp\s*top\s*10(?!.*\b(llm|api|ml)\b)", re.I),
        [
            (
                re.compile(r"access control|a01", re.I),
                [
                    "broken object level authorization",
                    "broken function level authorization",
                    "overly permissive authorization",
                ],
            ),
            (
                re.compile(r"crypto|a02|a04", re.I),
                ["cryptographic failures", "secrets management"],
            ),
            (
                re.compile(r"inject|a03|a05", re.I),
                ["injection", "ssrf", "server side request forgery"],
            ),
            (
                re.compile(r"misconfig|a05|a02", re.I),
                ["security misconfiguration", "insecure workload configurations"],
            ),
            (
                re.compile(r"auth|a07", re.I),
                ["broken authentication", "authentication failures"],
            ),
            (
                re.compile(r"log|a09", re.I),
                ["inadequate logging and monitoring", "logging and alerting"],
            ),
            (
                re.compile(r"component|a06|supply", re.I),
                [
                    "vulnerable and outdated components",
                    "supply chain vulnerabilities",
                    "improper inventory management",
                ],
            ),
        ],
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


def _phrases_for_node(name: str, section: str, section_id: str) -> List[str]:
    blob = f"{section_id} {section}"
    out: List[str] = []
    for name_pat, rules in _ENRICHMENTS:
        if not name_pat.search(name or ""):
            continue
        for sec_pat, phrases in rules:
            if sec_pat.search(blob):
                out.extend(phrases)
    # stable unique
    seen = set()
    uniq: List[str] = []
    for p in out:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


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
        print("DEV_DATABASE_URL required", file=sys.stderr)
        return 2

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import Node

    db_connect(cache)
    name_pats = [p for p, _ in _ENRICHMENTS]
    nodes = sqla.session.query(Node).all()
    updated = 0
    skipped = 0
    for node in nodes:
        if not any(p.search(node.name or "") for p in name_pats):
            continue
        extra = _phrases_for_node(
            node.name or "", node.section or "", node.section_id or ""
        )
        if not extra:
            skipped += 1
            continue
        meta: Dict[str, Any] = {}
        if isinstance(node.metadata_json, dict):
            meta = dict(node.metadata_json)
        oie = dict(meta.get("oie") or {}) if isinstance(meta.get("oie"), dict) else {}
        existing = [str(x) for x in (oie.get("phrases") or []) if x]
        merged = list(existing)
        for p in extra:
            if p.lower() not in {x.lower() for x in merged}:
                merged.append(p)
        if merged == existing:
            skipped += 1
            continue
        oie["phrases"] = merged
        if node.section and not oie.get("section_title"):
            oie["section_title"] = node.section
        meta["oie"] = oie
        print(
            f"  {node.name}|{node.section_id}: +{len(merged) - len(existing)} phrases",
            flush=True,
        )
        updated += 1
        if not args.dry_run:
            node.metadata_json = meta

    if not args.dry_run:
        sqla.session.commit()
    print(json.dumps({"updated": updated, "skipped": skipped, "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
