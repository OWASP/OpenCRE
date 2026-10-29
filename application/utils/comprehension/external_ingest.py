"""Crawl one external site and write it as raw chunks (shared by the CLI and the scheduler job)."""

from __future__ import annotations

from typing import Any, List

from application.utils.comprehension import external, web_source
from application.utils.comprehension.cost import CHARS_PER_TOKEN, PRICE


def summarize(spec: external.ExternalSpec, chunks: List[Any], result: Any) -> str:
    chars = sum(len(c[2]) for c in chunks)
    tokens = chars / CHARS_PER_TOKEN
    lines = [
        f"{spec.id}: {len(result.pages)} pages, {len(chunks)} chunks, "
        f"~{int(tokens)} tokens, est. embedding cost ${tokens * PRICE['embed_in'] / 1e6:.4f} "
        f"({result.requests} requests, sitemap={'yes' if result.used_sitemap else 'no'}, "
        f"{result.not_modified} not modified, {len(result.skipped)} skipped)"
    ]
    if getattr(result, "stopped", ""):
        lines.append(f"  STOPPED EARLY: {result.stopped} (partial crawl)")
    for page in result.pages:
        n = sum(1 for c in chunks if c[0] == page.url)
        lines.append(f"  page {page.url}  chunks={n}  {page.title[:60]!r}")
    for url, why in result.skipped:
        lines.append(f"  skipped {url}  ({why})")
    return "\n".join(lines)


def ingest_spec(
    spec: external.ExternalSpec,
    *,
    apply: bool,
    max_pages: int = 0,
    skip_unchanged: bool = False,
    enrich: bool = False,
    workers: int = 8,
    database: Any = None,
    embed: Any = None,
    enrich_fn: Any = None,
) -> dict:
    """Crawl one site and (when ``apply``) write its chunks. Returns counts for the caller/scheduler."""
    from application.utils.comprehension import store

    chunks, result = web_source.crawl_chunks(
        spec, max_pages=max_pages or None, write_cache=apply
    )
    print(summarize(spec, chunks, result), flush=True)
    written = 0
    if apply and chunks:
        slug = external.slug_for(spec)
        if skip_unchanged:
            before = len(chunks)
            chunks = store.changed_chunks(database, slug, chunks)
            print(f"{slug}: {len(chunks)}/{before} chunks new or changed", flush=True)
        enriched = None
        if enrich and enrich_fn is not None:
            enriched = store.enrich_chunks(slug, chunks, enrich_fn, workers=16)
        written = store.write_raw(
            database,
            slug,
            chunks,
            embed,
            workers=workers,
            enriched=enriched,
            url_for=lambda p: p,
        )
        print(f"{slug}: raw chunks written: {written}", flush=True)
    return {"pages": len(result.pages), "chunks": len(chunks), "written": written}
