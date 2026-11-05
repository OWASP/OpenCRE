#!/usr/bin/env python
"""Benchmark the two C.1 retriever backends (Week 3, PR 3).

Times in-memory cosine vs pgvector over the real CRE hub for a set of probe
queries, and checks they agree on the top-1. The in-memory backend always
runs (it only needs the embeddings already loaded); the pgvector backend runs
only when the DB is Postgres with the ``embedding_vec`` column present —
otherwise it is reported as skipped, never silently passed.

Usage:
    python scripts/benchmark_retriever.py --cache_file standards_cache.sqlite \\
        [--queries "password storage" "access control" ...] [--runs 5]
"""

import argparse
import os
import sys
import time
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from application.cmd.cre_main import db_connect
from application.defs import cre_defs
from application.prompt_client import prompt_client
from application.utils.librarian.candidate_retriever import (
    CandidatePool,
    PgVectorRetriever,
    build_retriever,
    RetrieverBackend,
)
from application.utils.librarian.config_loader import load_config

_DEFAULT_QUERIES = [
    "Verify that user-set passwords are at least 12 characters in length.",
    "Enforce least privilege for all access control decisions.",
    "Do not use broken cryptographic algorithms such as MD5 or SHA-1.",
    "Protect against cross-site scripting in all rendered output.",
]


def _time_backend(retriever, queries: List[str], runs: int) -> float:
    # Warm up (model/index load), then take the best wall-clock of `runs`.
    retriever.retrieve(queries[0])
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        for q in queries:
            retriever.retrieve(q)
        best = min(best, time.perf_counter() - start)
    return best


def _pgvector_available(database) -> bool:
    """True only on Postgres with the embedding_vec column present."""
    return bool(database.can_use_pgvector_similarity())


def main(argv: List[str]) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Benchmark C.1 retriever backends")
    parser.add_argument("--cache_file", default="standards_cache.sqlite")
    parser.add_argument("--queries", nargs="*", default=_DEFAULT_QUERIES)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--top_k", type=int, default=cfg.top_k_retrieval)
    args = parser.parse_args(argv)

    database = db_connect(path=args.cache_file)
    ph = prompt_client.PromptHandler(database=database)
    cre_embeddings = database.get_embeddings_by_doc_type(cre_defs.Credoctypes.CRE.value)
    print(f"CRE hub: {len(cre_embeddings)} vectors; {len(args.queries)} probe queries")

    in_mem = build_retriever(
        RetrieverBackend.in_memory,
        embed_fn=ph.get_text_embeddings,
        top_k=args.top_k,
        threshold=cfg.link_threshold,
        pool=CandidatePool.from_mapping(cre_embeddings),
    )
    in_mem_time = _time_backend(in_mem, args.queries, args.runs)
    print(f"in_memory : {in_mem_time * 1000:8.1f} ms / {len(args.queries)} queries")

    if not _pgvector_available(database):
        print(
            "pgvector  : SKIPPED (needs Postgres + embedding_vec; SQLite cannot "
            "run <=> — use CRE_LIBRARIAN_RETRIEVER_BACKEND=in_memory or "
            "postgresql://… after Alembic c7d8e9f0a1b2)"
        )
        return 0

    pg = PgVectorRetriever(
        embed_fn=ph.get_text_embeddings,
        connection=database.session.connection(),
        top_k=args.top_k,
        threshold=cfg.link_threshold,
    )
    pg_time = _time_backend(pg, args.queries, args.runs)
    print(f"pgvector  : {pg_time * 1000:8.1f} ms / {len(args.queries)} queries")

    # Agreement check: do the backends pick the same top-1 per query?
    agree = sum(
        in_mem.retrieve(q).candidates[0].cre_id == pg.retrieve(q).candidates[0].cre_id
        for q in args.queries
        if in_mem.retrieve(q).candidates and pg.retrieve(q).candidates
    )
    print(f"top-1 agreement: {agree}/{len(args.queries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
