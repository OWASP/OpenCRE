"""Persist digests as embedded evidence documents (no schema change).

Documents live in the existing OWASP-agent evidence channel under
``owasp-agent://evidence/comprehension-<repo>-...`` so the existing similarity
router retrieves them; synthesis (``synthesize.py``) combines the top hits.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

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


ENRICH_SYSTEM = (
    "You index ONE chunk of an OWASP repository so questions about it can be found. Respond with JSON "
    'only: {"context": "<one sentence: which project/document/section this chunk belongs to and what '
    'it is about; use only the given text>", "questions": ["<3 specific questions a user might ask '
    'that this chunk answers>"]}.'
)
RELATED = "\n\nRelated questions:"


def enrich_chunks(
    repo: str,
    chunks: List[Tuple[str, int, str]],
    llm: Callable[[str, str], str],
    *,
    workers: int = 16,
) -> Dict[Tuple[str, int], Tuple[str, List[str]]]:
    """(path, idx) -> (context sentence, likely questions), via a cheap model; failures are skipped."""
    from concurrent.futures import ThreadPoolExecutor

    from application.utils.comprehension.extras import parse_json

    starts: Dict[str, str] = {}
    for path, idx, text in sorted(chunks, key=lambda c: (c[0], c[1])):
        starts.setdefault(path, text)

    def one(c: Tuple[str, int, str]):
        path, idx, text = c
        try:
            d = parse_json(
                llm(
                    ENRICH_SYSTEM,
                    f"Project: {repo}\nFile: {path}\nDocument start: {starts[path][:400]}\n\nChunk:\n{text[:3500]}",
                )
            )
        except Exception:
            return (path, idx), None
        ctx = str(d.get("context") or "").strip()
        qs = [str(q).strip() for q in (d.get("questions") or []) if str(q).strip()][:3]
        return (path, idx), ((ctx, qs) if ctx or qs else None)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return {k: v for k, v in pool.map(one, chunks) if v}


def raw_documents(
    repo: str,
    chunks: List[Tuple[str, int, str]],
    github_base: str = "https://github.com",
    enriched: Optional[Dict[Tuple[str, int], Tuple[str, List[str]]]] = None,
    url_for: Optional[Callable[[str], str]] = None,
) -> List[Tuple[str, str, List[str]]]:
    """Source chunks as retrievable documents (detail recall that summaries lose).

    ``url_for(path)`` overrides the citation URL for sources that are not repo files (e.g. Nest).
    """
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
                _raw_text(family, path, text, (enriched or {}).get((path, idx))),
                [
                    (
                        url_for(path)
                        if url_for
                        else f"{github_base}/{repo}/blob/HEAD/{path}"
                    )
                ],
            )
        )
    return out


def _raw_text(
    family: str, path: str, text: str, extra: Optional[Tuple[str, List[str]]]
) -> str:
    if not extra:
        return f"{family} / {path}: {text}"
    ctx, qs = extra
    body = f"{family} / {path}: {ctx}\n{text}" if ctx else f"{family} / {path}: {text}"
    return body + (RELATED + " " + " | ".join(qs) if qs else "")


def write_raw(
    database: Any,
    repo: str,
    chunks: List[Tuple[str, int, str]],
    embed: Callable[[str], Any],
    *,
    workers: int = 8,
    dry_run: bool = False,
    enriched: Optional[Dict[Tuple[str, int], Tuple[str, List[str]]]] = None,
    url_for: Optional[Callable[[str], str]] = None,
) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT
    from application.utils.owasp_agent.meta_embeddings import (
        DOC_TYPE_EVIDENCE,
        evidence_url,
        upsert_channel_embedding,
    )

    docs = raw_documents(repo, chunks, enriched=enriched, url_for=url_for)
    bodies = [
        text + ("\n\nCitations: " + ", ".join(c) if c else "") for _, text, c in docs
    ]
    if dry_run:
        return len(docs)
    import time

    def embed_retry(body: str):
        for attempt in range(5):
            try:
                return list(embed(body))
            except (
                Exception
            ):  # noqa: BLE001 - provider 503/429: back off, then give up on this chunk
                if attempt == 4:
                    return None
                time.sleep(2**attempt)

    written = 0
    # Slices keep progress: a provider outage loses one slice, not the whole repo.
    for start in range(0, len(docs), 500):
        part_docs = docs[start : start + 500]
        part_bodies = bodies[start : start + 500]
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            vecs = list(pool.map(embed_retry, part_bodies))
        for (slug, _, _), body, vec in zip(part_docs, part_bodies, vecs):
            if vec is None:
                continue
            upsert_channel_embedding(
                database,
                source_channel=CHANNEL_AGENT,
                doc_type=DOC_TYPE_EVIDENCE,
                embeddings_url=evidence_url(slug),
                embedding_text=body,
                embeddings=vec,
            )
            written += 1
    return written


def changed_chunks(
    database: Any, repo: str, chunks: List[Tuple[str, int, str]]
) -> List[Tuple[str, int, str]]:
    """Chunks that are new or whose text differs from what is stored (resume / incremental ingest).

    A stored raw document holds the chunk text verbatim after the optional context line,
    so "unchanged" means the same document id exists and its content contains the chunk text.
    """
    from sqlalchemy import text as sql_text

    prefix = f"owasp-agent://evidence/{SLUG_PREFIX}{repo_slug(repo)}-raw-"
    rows = database.session.execute(
        sql_text(
            "SELECT embeddings_url, embeddings_content FROM embeddings "
            "WHERE embeddings_url LIKE :p"
        ),
        {"p": prefix + "%"},
    ).fetchall()
    stored = {r[0]: r[1] or "" for r in rows}
    out: List[Tuple[str, int, str]] = []
    for chunk in chunks:
        ((doc_id, _, _),) = raw_documents(repo, [chunk])
        url = f"owasp-agent://evidence/{doc_id}"
        if chunk[2] in stored.get(url, ""):
            continue
        out.append(chunk)
    return out


MAX_STALE_FRACTION = 0.5


def stale_raw_urls(
    database: Any, repo: str, chunks: List[Tuple[str, int, str]]
) -> List[str]:
    """Stored raw-document ids of ``repo`` that the current ``chunks`` no longer produce."""
    from sqlalchemy import text as sql_text

    prefix = f"owasp-agent://evidence/{SLUG_PREFIX}{repo_slug(repo)}-raw-"
    stored = [
        r[0]
        for r in database.session.execute(
            sql_text(
                "SELECT embeddings_url FROM embeddings WHERE embeddings_url LIKE :p"
            ),
            {"p": prefix + "%"},
        ).fetchall()
    ]
    current = {f"owasp-agent://evidence/{d[0]}" for d in raw_documents(repo, chunks)}
    return sorted(u for u in stored if u not in current)


def delete_stale_raw(
    database: Any,
    repo: str,
    chunks: List[Tuple[str, int, str]],
    *,
    force: bool = False,
) -> int:
    """Delete stored raw documents that a complete re-ingest no longer produces.

    Used for sources whose terms require removed content to disappear (YouTube videos made private
    or deleted). Guards: an empty run never deletes (an API outage must not wipe a source), and
    removing more than MAX_STALE_FRACTION of what is stored needs ``force``.
    """
    from sqlalchemy import text as sql_text

    if not chunks:
        raise ValueError("refusing to delete stale documents after an empty run")
    stale = stale_raw_urls(database, repo, chunks)
    if not stale:
        return 0
    current = len(chunks)
    if not force and len(stale) > MAX_STALE_FRACTION * (current + len(stale)):
        raise ValueError(
            f"{len(stale)} of {current + len(stale)} stored documents would be deleted; "
            "check the run was complete, then pass force"
        )
    for url in stale:
        database.session.execute(
            sql_text("DELETE FROM embeddings WHERE embeddings_url = :u"), {"u": url}
        )
    database.session.commit()
    return len(stale)
