#!/usr/bin/env python3
"""Populate Node ``document_metadata.oie`` via the LLM metadata enricher.

Targets CCM / ASVS / Top10 / NIST / Cheat Sheets / … so Module C neighbor
transfer can match brand-new catalogs without gold-seeding Links.

Usage:
  set -a && source tmp/oie.env && set +a
  export CRE_LIBRARIAN_METADATA_MODEL=gemini/gemini-2.5-pro
  PYTHONPATH=. python scripts/oie_enrich_node_metadata_llm.py
  PYTHONPATH=. python scripts/oie_enrich_node_metadata_llm.py --limit 20 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    for env_path in (ROOT / ".env", ROOT / "tmp" / "oie.env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if env_path.name == "oie.env":
                os.environ[k.strip()] = v.strip()
            else:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--cache-file", default="")
    parser.add_argument(
        "--model",
        default="",
        help="LiteLLM model (default: CRE_LIBRARIAN_METADATA_MODEL / gemini-2.5-pro)",
    )
    args = parser.parse_args()

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    _load_dotenv()
    if args.model:
        os.environ["CRE_LIBRARIAN_METADATA_MODEL"] = args.model
    os.environ.setdefault("CRE_LIBRARIAN_METADATA_MODEL", "gemini/gemini-2.5-pro")
    os.environ.setdefault("CRE_LIBRARIAN_EDITION_REMAP_MODEL", "gemini/gemini-2.5-pro")

    cache = (
        args.cache_file
        or os.environ.get("DEV_DATABASE_URL")
        or os.environ.get("CRE_CACHE_FILE")
        or ""
    )
    if not cache:
        print("DEV_DATABASE_URL required", file=sys.stderr)
        return 2

    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.utils.librarian.metadata_enricher import (
        MetadataEnrichmentService,
        default_metadata_llm_fn,
    )

    db_connect(cache)
    model = os.environ.get("CRE_LIBRARIAN_METADATA_MODEL", "gemini/gemini-2.5-pro")
    print(f"enriching with model={model} dry_run={args.dry_run}", flush=True)
    svc = MetadataEnrichmentService(
        session=sqla.session,
        llm_fn=default_metadata_llm_fn(model),
        force=args.force,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    stats = svc.run()
    report = {
        "model": model,
        "considered": stats.considered,
        "enriched": stats.enriched,
        "skipped_rich": stats.skipped_rich,
        "skipped_filter": stats.skipped_filter,
        "errors": stats.errors,
        "error_samples": stats.error_messages[:10],
        "dry_run": args.dry_run,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 1 if stats.errors and not stats.enriched else 0


if __name__ == "__main__":
    sys.exit(main())
