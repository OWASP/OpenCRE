#!/usr/bin/env python3
"""Report Standard embedding quality (prose vs junk/duplicate/stub).

Use this to pick CRE_LIBRARIAN_STANDARD_RETRIEVAL_FAMILIES before turning
dual retrieval on. Does not write anything.

  python scripts/audit_standard_embeddings.py --sqlite standards_cache.sqlite
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python scripts/audit_standard_embeddings.py` from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.librarian.embedding_quality import (  # noqa: E402
    rows_from_sqlite,
    summarize_families,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite", required=True, help="Path to standards_cache.sqlite"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of a table",
    )
    args = parser.parse_args()
    rows = list(rows_from_sqlite(args.sqlite))
    reports = summarize_families(rows)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": r.name,
                        "n": r.n,
                        "avg_chars": round(r.avg_chars, 1),
                        "unique_ratio": round(r.unique_ratio, 3),
                        "junk_ratio": round(r.junk_ratio, 3),
                        "stub_ratio": round(r.stub_ratio, 3),
                        "verdict": r.verdict,
                    }
                    for r in reports
                ],
                indent=2,
            )
        )
        return 0
    print(f"{'verdict':<10} {'n':>5} {'avg_chars':>10} {'unique':>7} {'junk':>6}  name")
    for r in reports:
        print(
            f"{r.verdict:<10} {r.n:5d} {r.avg_chars:10.0f} "
            f"{r.unique_ratio:7.2f} {r.junk_ratio:6.2f}  {r.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
