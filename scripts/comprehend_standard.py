#!/usr/bin/env python3
"""Digest a harvested standard with an LLM and store cited, embedded documents.

    python scripts/comprehend_standard.py --repo OWASP/SAMM [--dry-run] [--limit-docs N]

Env: CRE_COMPREHENSION_BULK_MODEL (default gemini/gemini-2.5-flash),
     CRE_COMPREHENSION_OVERVIEW_MODEL (default gemini/gemini-2.5-pro).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo", required=True, help="harvest source_repo, e.g. OWASP/SAMM"
    )
    ap.add_argument("--dry-run", action="store_true", help="no embeddings/DB writes")
    ap.add_argument("--limit-docs", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dump", help="write the digest JSON here")
    a = ap.parse_args()

    from application import create_app
    from application.database import db as db_mod
    from application.prompt_client import litellm_router, prompt_client
    from application.utils.comprehension import digest, sources, store

    bulk = litellm_router.system_user_fn(
        os.environ.get("CRE_COMPREHENSION_BULK_MODEL", "gemini/gemini-2.5-flash")
    )
    big = litellm_router.system_user_fn(
        os.environ.get("CRE_COMPREHENSION_OVERVIEW_MODEL", "gemini/gemini-2.5-pro")
    )
    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        docs = sources.load_repo_docs(database.session, a.repo)
        if a.limit_docs:
            docs = docs[: a.limit_docs]
        print(f"{a.repo}: {len(docs)} documents after noise filter", flush=True)
        d = digest.digest_standard(a.repo, docs, bulk, big, workers=a.workers)
        print(
            f"docs digested={len(d.docs)} claims(l1)={sum(len(x.claims) for x in d.docs)} "
            f"dropped(unverified)={sum(x.dropped for x in d.docs)} claims(l2)={len(d.claims)}",
            flush=True,
        )
        print("OVERVIEW:", d.overview[:600], flush=True)
        for c in d.claims[:12]:
            print(" -", c.statement, c.sources[:2], flush=True)
        if a.dump:
            Path(a.dump).write_text(
                json.dumps(d, default=lambda o: o.__dict__, indent=1)
            )
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
        n = store.write(database, d, handler.get_text_embeddings, dry_run=a.dry_run)
        print(f"documents {'planned' if a.dry_run else 'written'}: {n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
