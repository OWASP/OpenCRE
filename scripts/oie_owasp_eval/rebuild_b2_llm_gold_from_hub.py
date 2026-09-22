#!/usr/bin/env python3
"""Rebuild experimental B2 LLM Top 10 gold from hub ``OWASP Top10 for LLM`` Links.

Canonical eval gold is ``application/tests/fixtures/owasp_mappings/owasp_llm_top10_2025.json``
(AI-topic CREs from hub Links / AI Exchange theme bridges). This script can refresh
hub-backed rows; sections without hub Links stay provisional (see fixture provenance).

Usage:
  set -a && source tmp/oie.env && set +a
  PYTHONPATH=. python scripts/oie_owasp_eval/rebuild_b2_llm_gold_from_hub.py
  PYTHONPATH=. python scripts/oie_owasp_eval/rebuild_b2_llm_gold_from_hub.py \\
    --out application/tests/fixtures/owasp_mappings/owasp_llm_top10_2025.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = (
    ROOT / "scripts" / "oie_owasp_eval" / "fixtures" / "b2_gold" / "owasp_llm_top10_2025.json"
)

# Canonical LLM Top 10 2025 section order (titles/hyperlinks filled from prior gold).
_DEFAULT_SECTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "LLM01",
        "Prompt Injection",
        "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
    ),
    (
        "LLM02",
        "Sensitive Information Disclosure",
        "https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/",
    ),
    (
        "LLM03",
        "Supply Chain",
        "https://genai.owasp.org/llmrisk/llm032025-supply-chain/",
    ),
    (
        "LLM04",
        "Data and Model Poisoning",
        "https://genai.owasp.org/llmrisk/llm042025-data-and-model-poisoning/",
    ),
    (
        "LLM05",
        "Improper Output Handling",
        "https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/",
    ),
    (
        "LLM06",
        "Excessive Agency",
        "https://genai.owasp.org/llmrisk/llm062025-excessive-agency/",
    ),
    (
        "LLM07",
        "System Prompt Leakage",
        "https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/",
    ),
    (
        "LLM08",
        "Vector and Embedding Weaknesses",
        "https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/",
    ),
    (
        "LLM09",
        "Misinformation",
        "https://genai.owasp.org/llmrisk/llm092025-misinformation/",
    ),
    (
        "LLM10",
        "Unbounded Consumption",
        "https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/",
    ),
)


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
    existing: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Assemble gold rows; return (rows, gap_section_ids with empty cre_ids)."""
    prev = existing or {}
    rows: List[Dict[str, Any]] = []
    gaps: List[str] = []
    for sid, default_title, default_href in _DEFAULT_SECTIONS:
        old = prev.get(sid) or {}
        cre_ids = sorted({c for c in (hub_by_section.get(sid) or []) if c})
        if not cre_ids:
            gaps.append(sid)
        rows.append(
            {
                "section_id": sid,
                "section": str(old.get("section") or default_title),
                "hyperlink": str(old.get("hyperlink") or default_href),
                "cre_ids": cre_ids,
            }
        )
    return rows, gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_GOLD,
        help="Output gold JSON path (harness only)",
    )
    parser.add_argument(
        "--cache-file",
        default="",
        help="Postgres URL (default: DEV_DATABASE_URL / CRE_CACHE_FILE)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows/gaps without writing",
    )
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

    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.utils.librarian.aix_llm_link_seed import (
        hub_llm_external_ids_by_section,
    )

    db_connect(cache)
    hub = hub_llm_external_ids_by_section(sqla.session)
    existing = load_existing_gold(args.out)
    rows, gaps = build_gold_rows(hub, existing=existing)

    report = {
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
