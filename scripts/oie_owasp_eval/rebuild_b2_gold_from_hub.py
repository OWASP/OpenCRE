#!/usr/bin/env python3
"""Rebuild B2 gold JSON from hub Links for a known standard family.

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/rebuild_b2_gold_from_hub.py \\
    --catalog k8s_top10 --out scripts/oie_owasp_eval/fixtures/b2_gold/owasp_kubernetes_top10_2025.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]

# catalog_key → default section order (sid, title, href) when existing gold missing
_DEFAULTS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "llm_top10": (
        ("LLM01", "Prompt Injection", ""),
        ("LLM02", "Sensitive Information Disclosure", ""),
        ("LLM03", "Supply Chain", ""),
        ("LLM04", "Data and Model Poisoning", ""),
        ("LLM05", "Improper Output Handling", ""),
        ("LLM06", "Excessive Agency", ""),
        ("LLM07", "System Prompt Leakage", ""),
        ("LLM08", "Vector and Embedding Weaknesses", ""),
        ("LLM09", "Misinformation", ""),
        ("LLM10", "Unbounded Consumption", ""),
    ),
}


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


def load_existing_gold(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("section_id") or "").strip().upper().split(":")[0]
        if sid:
            out[sid] = row
    return out


def build_gold_rows(
    hub_by_section: Mapping[str, Sequence[str]],
    *,
    existing: Mapping[str, Mapping[str, Any]],
    defaults: Sequence[Tuple[str, str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    gaps: List[str] = []
    # Prefer existing gold section order; else defaults; else hub keys sorted.
    order: List[Tuple[str, str, str]] = []
    if existing:
        for sid, old in existing.items():
            order.append(
                (
                    sid,
                    str(old.get("section") or sid),
                    str(old.get("hyperlink") or ""),
                )
            )
    elif defaults:
        order = list(defaults)
    else:
        order = [(sid, sid, "") for sid in sorted(hub_by_section.keys())]

    seen: set[str] = set()
    for sid, default_title, default_href in order:
        key = sid.upper()
        if key in seen:
            continue
        seen.add(key)
        old = existing.get(key) or existing.get(sid) or {}
        cre_ids = sorted({c for c in (hub_by_section.get(key) or []) if c})
        if not cre_ids:
            gaps.append(key)
        row: Dict[str, Any] = {
            "section_id": key if not key.startswith("AISVS") else sid,
            "section": str(old.get("section") or default_title),
            "hyperlink": str(old.get("hyperlink") or default_href),
            "cre_ids": cre_ids,
        }
        if old.get("fallback_section_ids"):
            row["fallback_section_ids"] = old["fallback_section_ids"]
        rows.append(row)
    return rows, gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        required=True,
        help="Catalog key: llm_top10, k8s_top10, owasp_top10, api_top10, aisvs, …",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache-file", default="")
    parser.add_argument("--dry-run", action="store_true")
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
    from application.utils.librarian.standard_link_seed import (
        hub_external_ids_by_section,
    )

    db_connect(cache)
    hub = hub_external_ids_by_section(sqla.session, catalog_key=args.catalog)
    existing = load_existing_gold(args.out)
    rows, gaps = build_gold_rows(
        hub,
        existing=existing,
        defaults=_DEFAULTS.get(args.catalog, ()),
    )
    report = {
        "catalog": args.catalog,
        "sections": len(rows),
        "scorable": sum(1 for r in rows if r["cre_ids"]),
        "gaps": gaps,
        "hub_sections": sorted(hub.keys()),
        "out": str(args.out),
    }
    print(json.dumps(report, indent=2), flush=True)
    for row in rows:
        print(
            f"  {row['section_id']}: {row['cre_ids'] or '(gap — unscorable)'}",
            flush=True,
        )
    if args.dry_run:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
