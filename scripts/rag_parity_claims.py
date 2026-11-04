#!/usr/bin/env python3
"""TASK-14.15: extract knowledge_claim drafts from prose (no CRE graph writes).

Example:
  CRE_RAG_PARITY_CLAIMS=1 python scripts/rag_parity_claims.py \\
    --source-file path.txt --source-ref ASVS:V2.1.1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-file", required=True, help="UTF-8 prose file")
    p.add_argument("--source-ref", default="", help="Provenance label")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print verified claims JSON; never write DB",
    )
    args = p.parse_args(argv)

    from application.utils.rag_parity.flags import load_flags
    from application.utils.rag_parity.phase5_claims import (
        claims_for_persist,
        extract_claims,
    )

    cfg = load_flags()
    if not cfg.knowledge_claim_extract:
        print(
            "CRE_RAG_PARITY_CLAIMS is off — set CRE_RAG_PARITY_CLAIMS=1",
            file=sys.stderr,
        )
        return 2

    source = Path(args.source_file).read_text(encoding="utf-8")
    from application.utils.comprehension import flags as cx_flags

    llm = cx_flags.helper_llm()
    if llm is None:
        print("helper LLM unavailable", file=sys.stderr)
        return 3

    drafts = extract_claims(source, llm_fn=llm, source_ref=args.source_ref)
    verified = claims_for_persist(drafts)
    payload = [
        {
            "claim": d.claim,
            "quote": d.quote,
            "confidence": d.confidence,
            "source_ref": d.source_ref,
            "status": d.status,
        }
        for d in verified
    ]
    print(json.dumps({"verified": payload, "dropped": len(drafts) - len(verified)}))
    if not args.dry_run:
        print(
            "DB persist not implemented in this CLI — use --dry-run "
            "(table migration a1b2c3d4e5f7 exists for review queue).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
