"""Persist digests as embedded evidence documents (no schema change).

Documents live in the existing OWASP-agent evidence channel under
``owasp-agent://evidence/comprehension-<repo>-...`` so the existing similarity
router retrieves them; synthesis (``synthesize.py``) combines the top hits.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, List, Tuple

from application.utils.comprehension.digest import StandardDigest

SLUG_PREFIX = "comprehension-"


def repo_slug(repo: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")


def documents(
    d: StandardDigest, github_base: str = "https://github.com"
) -> List[Tuple[str, str, List[str]]]:
    """Return (slug, embed_text, citations) for the overview and each claim."""
    base = repo_slug(d.repo)
    family = d.repo.split("/")[-1]

    def cites(paths: List[str]) -> List[str]:
        return [f"{github_base}/{d.repo}/blob/HEAD/{p}" for p in paths[:5]]

    docs: List[Tuple[str, str, List[str]]] = []
    if d.overview:
        allp = [x.path for x in d.docs][:5]
        docs.append(
            (
                f"{SLUG_PREFIX}{base}-overview",
                f"Overview of {family} ({d.repo}): {d.overview}",
                cites(allp),
            )
        )
    for i, c in enumerate(d.claims):
        docs.append(
            (
                f"{SLUG_PREFIX}{base}-claim-{i:03d}",
                f"{family}: {c.statement}",
                cites(c.sources),
            )
        )
    for dd in d.docs:
        for j, c in enumerate(dd.claims):
            dslug = re.sub(r"[^a-z0-9]+", "-", dd.path.lower()).strip("-")[:60]
            docs.append(
                (
                    f"{SLUG_PREFIX}{base}-dclaim-{dslug}-{j:02d}",
                    f"{family} / {dd.path}: {c.statement}",
                    cites([dd.path]),
                )
            )
        if dd.summary:
            slug = f"{SLUG_PREFIX}{base}-doc-{re.sub(r'[^a-z0-9]+', '-', dd.path.lower()).strip('-')[:80]}"
            docs.append((slug, f"{family} / {dd.path}: {dd.summary}", cites([dd.path])))
    return docs


def write(
    database: Any,
    d: StandardDigest,
    embed: Callable[[str], Any],
    *,
    dry_run: bool = False,
) -> int:
    from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT
    from application.utils.owasp_agent.meta_embeddings import (
        DOC_TYPE_EVIDENCE,
        evidence_url,
        upsert_channel_embedding,
    )

    n = 0
    for slug, text, citations in documents(d):
        body = text + ("\n\nCitations: " + ", ".join(citations) if citations else "")
        if not dry_run:
            upsert_channel_embedding(
                database,
                source_channel=CHANNEL_AGENT,
                doc_type=DOC_TYPE_EVIDENCE,
                embeddings_url=evidence_url(slug),
                embedding_text=body,
                embeddings=list(embed(body)),
            )
        n += 1
    return n


def raw_documents(
    repo: str,
    chunks: List[Tuple[str, int, str]],
    github_base: str = "https://github.com",
) -> List[Tuple[str, str, List[str]]]:
    """Source chunks as retrievable documents (detail recall that summaries lose)."""
    base = repo_slug(repo)
    family = repo.split("/")[-1]
    out: List[Tuple[str, str, List[str]]] = []
    for path, idx, text in chunks:
        pslug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")[:50]
        phash = hashlib.sha1(path.encode()).hexdigest()[
            :8
        ]  # long paths must not collide
        out.append(
            (
                f"{SLUG_PREFIX}{base}-raw-{pslug}-{phash}-{idx:03d}",
                f"{family} / {path}: {text}",
                [f"{github_base}/{repo}/blob/HEAD/{path}"],
            )
        )
    return out


def write_raw(
    database: Any,
    repo: str,
    chunks: List[Tuple[str, int, str]],
    embed: Callable[[str], Any],
    *,
    workers: int = 8,
    dry_run: bool = False,
) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT
    from application.utils.owasp_agent.meta_embeddings import (
        DOC_TYPE_EVIDENCE,
        evidence_url,
        upsert_channel_embedding,
    )

    docs = raw_documents(repo, chunks)
    bodies = [
        text + ("\n\nCitations: " + ", ".join(c) if c else "") for _, text, c in docs
    ]
    if dry_run:
        return len(docs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        vecs = list(pool.map(lambda b: list(embed(b)), bodies))
    for (slug, _, _), body, vec in zip(docs, bodies, vecs):
        upsert_channel_embedding(
            database,
            source_channel=CHANNEL_AGENT,
            doc_type=DOC_TYPE_EVIDENCE,
            embeddings_url=evidence_url(slug),
            embedding_text=body,
            embeddings=vec,
        )
    return len(docs)
