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
    ap.add_argument(
        "--exclude", nargs="*", default=[], help="source_repos to skip (held-out)"
    )
    ap.add_argument(
        "--raw", action="store_true", help="embed raw source chunks (no LLM)"
    )
    ap.add_argument(
        "--estimate",
        action="store_true",
        help="no LLM calls: count documents/tokens and print an estimated cost",
    )
    ap.add_argument(
        "--skip-done",
        action="store_true",
        help="skip repos whose comprehension overview already exists",
    )
    ap.add_argument(
        "--enrich",
        action="store_true",
        help="with --raw: add an LLM context sentence and likely questions to each chunk's embedded text",
    )
    ap.add_argument(
        "--supplement",
        action="store_true",
        help="with --raw: also index repo markdown files the harvester skipped (git clone)",
    )
    ap.add_argument(
        "--repos-file", help="file with one repository per line (OWASP/x or x)"
    )
    ap.add_argument(
        "--clone-only",
        action="store_true",
        help="with --raw: take the chunks from a shallow clone instead of the harvest (repos never harvested)",
    )
    ap.add_argument(
        "--wiki", action="store_true", help="with --raw: also index the GitHub wiki"
    )
    ap.add_argument(
        "--wiki-only", action="store_true", help="with --raw: only the GitHub wiki"
    )
    ap.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="with --raw: cap chunks per repository (0 = no cap)",
    )
    ap.add_argument(
        "--supplement-only",
        action="store_true",
        help="with --supplement: write only the skipped files' chunks (repo already indexed)",
    )
    ap.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="with --raw: only process chunks that are new or changed (resume / incremental)",
    )
    ap.add_argument("--profile", choices=["standard", "people"], default="standard")
    ap.add_argument("--dry-run", action="store_true", help="no embeddings/DB writes")
    ap.add_argument("--limit-docs", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--dump", help="write the digest JSON here")
    a = ap.parse_args()

    usage = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}

    def _meter(kwargs, response, start, end):  # litellm success callback
        u = getattr(response, "usage", None)
        usage["calls"] += 1
        usage["in"] += int(getattr(u, "prompt_tokens", 0) or 0)
        usage["out"] += int(getattr(u, "completion_tokens", 0) or 0)
        usage["cost"] += float((kwargs or {}).get("response_cost") or 0.0)

    import litellm

    litellm.success_callback = [_meter]

    from application import create_app
    from application.database import db as db_mod
    from application.prompt_client import litellm_router, prompt_client
    from application.utils.comprehension import digest, sources, store

    # Thinking tokens bill as output; per-document extraction does not need them.
    think_off = (os.environ.get("CRE_COMPREHENSION_THINKING", "off") or "off") != "on"
    bulk = litellm_router.system_user_fn(
        os.environ.get("CRE_COMPREHENSION_BULK_MODEL", "gemini/gemini-2.5-flash"),
        extra_try_kwargs={"reasoning_effort": "disable"} if think_off else None,
    )
    big = litellm_router.system_user_fn(
        os.environ.get("CRE_COMPREHENSION_OVERVIEW_MODEL", "gemini/gemini-2.5-pro")
    )
    app = create_app(mode=os.environ.get("FLASK_CONFIG", "production"))
    with app.app_context():
        database = db_mod.Node_collection()
        repos = list(a.repo)
        if a.repos_file:
            with open(a.repos_file, encoding="utf-8") as fh:
                for line in fh:
                    name = line.strip()
                    if name:
                        repos.append(name if "/" in name else f"OWASP/{name}")
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
        if a.skip_done:
            from application.utils.comprehension.store import SLUG_PREFIX, repo_slug

            done = {
                r
                for r in repos
                if database.session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT 1 FROM embeddings WHERE embeddings_url = :u LIMIT 1"
                    ),
                    {
                        "u": f"owasp-agent://evidence/{SLUG_PREFIX}{repo_slug(r)}-overview"
                    },
                ).first()
            }
            repos = [r for r in repos if r not in done]
            print(f"skipping {len(done)} repos already comprehended", flush=True)
        if a.estimate:
            from application.utils.comprehension.cost import estimate_repo, report

            rows = []
            for repo in repos:
                docs = sources.load_repo_docs(database.session, repo)
                ch = sources.chunks_for_repo(database.session, repo)
                rows.append(estimate_repo(repo, docs, ch))
            print(report(rows), flush=True)
            return 0
        for repo in repos:
            try:
                if a.raw:
                    import tempfile

                    clone_dir = (
                        os.environ.get("CRE_COMPREHENSION_CLONE_DIR")
                        or tempfile.mkdtemp()
                    )
                    if a.clone_only or a.wiki_only:
                        ch = []
                    else:
                        ch = sources.chunks_for_repo(database.session, repo)
                    if a.clone_only:
                        ch = sources.supplement_chunks(repo, set(), clone_dir)
                        print(f"{repo}: {len(ch)} chunks from the clone", flush=True)
                    if a.wiki or a.wiki_only:
                        wiki = sources.wiki_chunks(repo, clone_dir)
                        print(f"{repo}: {len(wiki)} wiki chunks", flush=True)
                        ch = ch + wiki
                    if a.max_chunks and len(ch) > a.max_chunks:
                        print(
                            f"{repo}: CAPPED {len(ch)} -> {a.max_chunks} chunks",
                            flush=True,
                        )
                        ch = ch[: a.max_chunks]
                    if a.supplement:
                        import tempfile

                        extra = sources.supplement_chunks(
                            repo,
                            {p for p, _, _ in ch},
                            os.environ.get("CRE_COMPREHENSION_CLONE_DIR")
                            or tempfile.mkdtemp(),
                        )
                        print(
                            f"{repo}: +{len(extra)} chunks from skipped files",
                            flush=True,
                        )
                        ch = extra if a.supplement_only else ch + extra
                    if a.skip_unchanged:
                        before = len(ch)
                        ch = store.changed_chunks(database, repo, ch)
                        print(
                            f"{repo}: {len(ch)}/{before} chunks new or changed",
                            flush=True,
                        )
                    enriched = None
                    if a.enrich and not a.dry_run:
                        lite = litellm_router.system_user_fn(
                            os.environ.get(
                                "CRE_COMPREHENSION_ENRICH_MODEL",
                                "gemini/gemini-2.5-flash-lite",
                            ),
                            extra_try_kwargs={"reasoning_effort": "disable"},
                        )
                        enriched = store.enrich_chunks(repo, ch, lite, workers=16)
                        print(
                            f"{repo}: enriched {len(enriched)}/{len(ch)} chunks",
                            flush=True,
                        )
                    n = store.write_raw(
                        database,
                        repo,
                        ch,
                        handler.get_text_embeddings,
                        workers=a.workers,
                        dry_run=a.dry_run,
                        enriched=enriched,
                        url_for=(
                            (
                                lambda p, r=repo: (
                                    f"https://github.com/{r}/wiki"
                                    if p.startswith("wiki/")
                                    else f"https://github.com/{r}/blob/HEAD/{p}"
                                )
                            )
                        ),
                    )
                    print(
                        f"{repo}: raw chunks {'planned' if a.dry_run else 'written'}: {n}",
                        flush=True,
                    )
                    continue
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
    print(
        f"METERED llm_calls={usage['calls']} tokens_in={usage['in']} tokens_out={usage['out']} "
        f"llm_cost_usd={usage['cost']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
