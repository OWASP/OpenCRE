#!/usr/bin/env python3
"""Delete already-indexed comprehension chunks whose source file is noise (image READMEs, vendored code, ...).

Dry run by default; pass --apply to delete. Uses the same path rules as ingestion
(application/utils/comprehension/paths.py), so a re-ingest never brings them back.

    python scripts/prune_noise_chunks.py            # count + sample
    python scripts/prune_noise_chunks.py --apply
"""

import argparse
import re
import sys

from application import create_app, sqla
from sqlalchemy import text

from application.utils.comprehension.paths import is_asset_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    app = create_app(mode="production")
    with app.app_context():
        with sqla.session.get_bind().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, embeddings_url, embeddings_content FROM embeddings "
                    "WHERE embeddings_url LIKE 'owasp-agent://evidence/comprehension-%-raw-%'"
                )
            ).fetchall()
            doomed, sample = [], []
            for r in rows:
                m = re.search(
                    r"Citations:\s*(https?://[^\s,]+)", r.embeddings_content or ""
                )
                if m and is_asset_path(m.group(1).split("/blob/HEAD/", 1)[-1]):
                    doomed.append(r.id)
                    if len(sample) < 8:
                        sample.append(m.group(1))
            print(f"raw chunks: {len(rows)}; noise chunks: {len(doomed)}")
            for s in sample:
                print("  e.g.", s)
            if args.apply and doomed:
                for i in range(0, len(doomed), 500):
                    conn.execute(
                        text("DELETE FROM embeddings WHERE id = ANY(:ids)"),
                        {"ids": doomed[i : i + 500]},
                    )
                conn.commit()
                print(f"deleted {len(doomed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
