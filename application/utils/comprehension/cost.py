"""Cost estimate for comprehension runs (no LLM calls). Prices are USD per million tokens."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

# Public Gemini list prices (verify against the current price sheet before relying on them).
PRICE = {
    "flash_in": 0.30,
    "flash_out": 2.50,
    "pro_in": 1.25,
    "pro_out": 10.00,
    "embed_in": 0.15,
}
CHARS_PER_TOKEN = 4.0
DOC_OUT_TOKENS = 900  # per-document JSON (summary + claims), thinking off
OVERVIEW_OUT_TOKENS = 2500
DIGEST_TOKENS_PER_DOC = 350  # what the overview call reads per document
MAX_OVERVIEW_IN = 750_000  # tokens (3M-char cap in digest_standard)
EMBED_TOKENS_PER_DOC = 450  # claims, summaries and overview are short
EMBED_DOCS_PER_DOC = 14  # level-1 claims + summary per document (rough)


def estimate_repo(
    repo: str, docs: Sequence[Any], chunks: Sequence[Any]
) -> Dict[str, Any]:
    chars = sum(len(d.text) for d in docs)
    tok_in = chars / CHARS_PER_TOKEN
    n = len(docs)
    ov_in = min(n * DIGEST_TOKENS_PER_DOC, MAX_OVERVIEW_IN)
    digest = (
        tok_in * PRICE["flash_in"] / 1e6 + n * DOC_OUT_TOKENS * PRICE["flash_out"] / 1e6
    )
    overview = (
        ov_in * PRICE["pro_in"] / 1e6 + OVERVIEW_OUT_TOKENS * PRICE["pro_out"] / 1e6
    )
    emb_tokens = (
        n * EMBED_DOCS_PER_DOC * EMBED_TOKENS_PER_DOC
        + sum(len(c[2]) for c in chunks) / CHARS_PER_TOKEN
    )
    embed = emb_tokens * PRICE["embed_in"] / 1e6
    raw_embed = (
        sum(len(c[2]) for c in chunks) / CHARS_PER_TOKEN * PRICE["embed_in"] / 1e6
    )
    return {
        "repo": repo,
        "docs": n,
        "chunks": len(chunks),
        "chars": chars,
        "digest": digest,
        "overview": overview,
        "embed": embed,
        "raw_only": raw_embed,
        "total": digest + overview + embed,
    }


def report(rows: List[Dict[str, Any]]) -> str:
    lines = [
        f"{'repo':58s} {'docs':>5s} {'chunks':>6s} {'digest':>7s} {'ovrvw':>6s} {'embed':>6s} {'total':>7s} {'raw-only':>8s}"
    ]
    for r in sorted(rows, key=lambda r: -r["total"])[:40]:
        lines.append(
            f"{r['repo'][:58]:58s} {r['docs']:5d} {r['chunks']:6d} {r['digest']:7.2f} {r['overview']:6.2f} {r['embed']:6.2f} {r['total']:7.2f} {r['raw_only']:8.2f}"
        )
    t = {
        k: sum(r[k] for r in rows)
        for k in ("docs", "chunks", "digest", "overview", "embed", "total", "raw_only")
    }
    lines.append(
        f"TOTAL repos={len(rows)} docs={t['docs']} chunks={t['chunks']}  digest=${t['digest']:.2f} "
        f"overview=${t['overview']:.2f} embed=${t['embed']:.2f}  ALL=${t['total']:.2f}  RAW-ONLY=${t['raw_only']:.2f}"
    )
    return "\n".join(lines)
