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
        "--repo", nargs="*", default=[], help="harvest source_repo, e.g. OWASP/SAMM"
    )
    ap.add_argument(
        "--like", help="SQL ILIKE on source_repo, e.g. 'OWASP/www-revent-%%'"
    )
    ap.add_argument(
        "--top",
        type=int,
        default=0,
        help="with --like: only the N repos with most chunks",
    )
    ap.add_argument("--exclude", nargs="*", default=[], help="source_repos to skip (held-out)")
    ap.add_argument("--profile", choices=["standard", "people"], default="standard")
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
        repos = list(a.repo)
        if a.like:
            from sqlalchemy import func

            q = (
                database.session.query(db_mod.HarvestInput.source_repo)
                .filter(db_mod.HarvestInput.source_repo.ilike(a.like))
                .group_by(db_mod.HarvestInput.source_repo)
                .order_by(func.count().desc())
            )
            if a.top:
                q = q.limit(a.top)
            repos += [r[0] for r in q]
        repos = [r for r in dict.fromkeys(repos) if r not in set(a.exclude)]
        handler = prompt_client.PromptHandler(database, load_all_embeddings=False)
        system = digest.PEOPLE_SYSTEM if a.profile == "people" else digest.DOC_SYSTEM
        for repo in repos:
            try:
                docs = sources.load_repo_docs(database.session, repo)
                if a.limit_docs:
                    docs = docs[: a.limit_docs]
                print(f"{repo}: {len(docs)} documents after noise filter", flush=True)
                d = digest.digest_standard(
                    repo, docs, bulk, big, workers=a.workers, system=system
                )
                print(
                    f"docs digested={len(d.docs)} claims(l1)={sum(len(x.claims) for x in d.docs)} "
                    f"dropped(unverified)={sum(x.dropped for x in d.docs)} claims(l2)={len(d.claims)}",
                    flush=True,
                )
                if a.dump:
                    Path(a.dump).write_text(
                        json.dumps(d, default=lambda o: o.__dict__, indent=1)
                    )
                n = store.write(
                    database, d, handler.get_text_embeddings, dry_run=a.dry_run
                )
                print(
                    f"documents {'planned' if a.dry_run else 'written'}: {n}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{repo}: FAILED {str(exc)[:200]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
