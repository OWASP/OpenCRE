"""Bridge: crawled websites -> Module A harvest records -> the one OIE pipeline.

A repo is harvested by Module A into ``harvest_input``; Module B filters it,
Module C maps it to CREs, ``decision_queue`` holds the verdicts and the filer
(or a reviewer) writes the graph. A website now takes the same road: this
module turns the crawler's chunks into the same ``harvest_input`` rows, with
``source.type = "url"`` instead of ``"github"``. Nothing downstream branches on
repo-versus-website any more than it has to.

The crawler's raw chunks (agent retrieval index) are untouched: a page is
indexed there AND offered to the graph, and Module B decides whether it is
security knowledge (events, talks and sponsor pages come back ``NOISE`` and
stop there; they stay searchable through the agent index).

Run order for a site::

    python scripts/ingest_external.py --id slsa --apply --oie-run-id slsa-1
    python scripts/run_oie_pipeline.py --skip-a --run_id slsa-1
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from application.database.db import HarvestInput
from application.utils.comprehension import external, web_source

SCHEMA_VERSION = "0.2.0"


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def chunks_to_payloads(
    spec: external.ExternalSpec,
    chunks: Iterable[Tuple[str, int, str]],
    titles: Dict[str, str],
    *,
    run_id: str,
    fetched_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Crawler chunks ``(path, index, text)`` -> Module B ``ChangeRecord`` payloads.

    Ids are stable for a given site, page and position, so re-staging the same
    crawl produces the same ``chunk_id`` values.
    """
    if spec.kind != external.KIND_SITE:
        raise ValueError("only external websites can be staged for the OIE pipeline")
    stamp = (fetched_at or datetime.now(timezone.utc)).isoformat()
    slug = external.slug_for(spec)

    by_page: Dict[str, List[Tuple[int, str]]] = {}
    for path, index, text in chunks:
        by_page.setdefault(path, []).append((index, text))

    payloads: List[Dict[str, Any]] = []
    for path, parts in by_page.items():
        url = external.page_url(spec, path)
        title = (titles.get(path) or titles.get(url) or "").strip()
        ordered = [text for _, text in sorted(parts, key=lambda p: p[0])]
        total = len(ordered)
        offset = 0
        for position, text in enumerate(ordered):
            payloads.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "chunk_id": f"{slug}:{_digest(url)}:{position}",
                    "artifact_id": f"{slug}:{url}",
                    "pipeline_run_id": run_id,
                    "text": text,
                    "span": {
                        "index": position,
                        "total": total,
                        "heading_path": [title] if title else [],
                        "start_char_idx": offset,
                        "end_char_idx": offset + len(text),
                    },
                    "source": {"type": "url", "url": url, "committed_at": stamp},
                    "locator": {"kind": "url", "id": url, "path": url},
                }
            )
            offset += len(text)
    return payloads


def stage_harvest(
    session: Any,
    run_id: str,
    payloads: Iterable[Dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    """Insert pending ``harvest_input`` rows; a page already staged for this run is skipped.

    Returns the number of rows written (or that would be written on a dry run).
    """
    if not run_id or not run_id.strip():
        raise ValueError("run_id must be non-empty")
    staged = {
        row[0]
        for row in session.query(HarvestInput.artifact_id)
        .filter(HarvestInput.pipeline_run_id == run_id)
        .all()
    }
    written = 0
    for payload in payloads:
        if payload["artifact_id"] in staged:
            continue
        written += 1
        if dry_run:
            continue
        session.add(
            HarvestInput(
                pipeline_run_id=run_id,
                status="pending",
                artifact_id=payload["artifact_id"],
                source_repo=None,
                payload=payload,
            )
        )
    if written and not dry_run:
        session.commit()
    return written


def stage_external(
    spec: external.ExternalSpec,
    *,
    run_id: str,
    apply: bool,
    max_pages: int = 0,
    session: Any = None,
    crawl_fn: Any = None,
) -> Dict[str, int]:
    """Crawl one approved site and stage it for the OIE pipeline (dry run by default)."""
    crawl = crawl_fn or web_source.crawl_chunks
    chunks, result = crawl(spec, max_pages=max_pages or None, write_cache=apply)
    titles = {page.url: page.title for page in result.pages}
    payloads = chunks_to_payloads(spec, chunks, titles, run_id=run_id)
    if session is None:
        from application import sqla

        session = sqla.session
    staged = stage_harvest(session, run_id, payloads, dry_run=not apply)
    counts = {"pages": len(result.pages), "chunks": len(chunks), "staged": staged}
    logger.info("staged external site for OIE", extra={"site": spec.id, **counts})
    return counts
