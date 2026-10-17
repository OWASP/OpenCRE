"""Persist digests as embedded evidence documents (no schema change).

Documents live in the existing OWASP-agent evidence channel under
``owasp-agent://evidence/comprehension-<repo>-...`` so the existing similarity
router retrieves them; synthesis (``synthesize.py``) combines the top hits.
"""

from __future__ import annotations

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
