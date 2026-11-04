"""Phase 4: modern rerank + contextual compression (env-gated).

Default off for prod. Staging may enable after ≥+3 pts ablation vs wrong-auto-link flat.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from application.utils.rag_parity.flags import RagParityFlags, load_flags

RerankFn = Callable[[str, Sequence[Tuple[str, str]]], List[Tuple[str, float]]]


@dataclass(frozen=True)
class RerankHit:
    doc_id: str
    text: str
    score: float


def default_rerank_provider() -> str:
    return os.environ.get("CRE_RAG_PARITY_RERANK_PROVIDER", "cohere").strip().lower()


def identity_rerank(
    query: str, docs: Sequence[Tuple[str, str]]
) -> List[Tuple[str, float]]:
    """Fallback when modern rerank disabled or provider unavailable."""
    _ = query
    n = max(len(docs), 1)
    return [(doc_id, float(n - i) / n) for i, (doc_id, _text) in enumerate(docs)]


def try_cohere_rerank(
    query: str, docs: Sequence[Tuple[str, str]]
) -> List[Tuple[str, float]]:
    """Optional Cohere Rerank; requires ``cohere`` + ``COHERE_API_KEY``."""
    import cohere  # type: ignore

    api_key = os.environ.get("COHERE_API_KEY", "")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY missing")
    client = cohere.Client(api_key)
    model = os.environ.get("CRE_RAG_PARITY_COHERE_RERANK_MODEL", "rerank-v3.5")
    texts = [t for _id, t in docs]
    resp = client.rerank(model=model, query=query, documents=texts, top_n=len(texts))
    out: List[Tuple[str, float]] = []
    for item in resp.results:
        doc_id, _ = docs[item.index]
        out.append((doc_id, float(item.relevance_score)))
    return out


def resolve_rerank_fn(
    flags: Optional[RagParityFlags] = None,
    *,
    override: Optional[RerankFn] = None,
) -> RerankFn:
    if override is not None:
        return override
    cfg = flags or load_flags()
    if not cfg.modern_rerank:
        return identity_rerank
    provider = default_rerank_provider()
    if provider == "cohere":

        def _call(
            query: str, docs: Sequence[Tuple[str, str]]
        ) -> List[Tuple[str, float]]:
            try:
                return try_cohere_rerank(query, docs)
            except Exception:  # noqa: BLE001
                return identity_rerank(query, docs)

        return _call
    return identity_rerank


def contextual_compress(
    hits: Sequence[RerankHit],
    *,
    max_chars: int,
    enabled: bool,
) -> List[RerankHit]:
    """Rerank-then-trim: keep highest-scoring hits until char budget exhausted."""
    if not enabled:
        return list(hits)
    ordered = sorted(hits, key=lambda h: h.score, reverse=True)
    out: List[RerankHit] = []
    used = 0
    for hit in ordered:
        text = hit.text or ""
        if used >= max_chars:
            break
        if used + len(text) > max_chars:
            text = text[: max(0, max_chars - used)].rstrip()
            if not text:
                break
        out.append(RerankHit(doc_id=hit.doc_id, text=text, score=hit.score))
        used += len(text)
    return out


def rerank_and_compress(
    query: str,
    docs: Sequence[Tuple[str, str]],
    *,
    flags: Optional[RagParityFlags] = None,
    rerank_fn: Optional[RerankFn] = None,
    max_chars: int = 6000,
) -> List[RerankHit]:
    cfg = flags or load_flags()
    fn = resolve_rerank_fn(cfg, override=rerank_fn)
    scored = fn(query, docs)
    by_id = {doc_id: text for doc_id, text in docs}
    hits = [
        RerankHit(doc_id=doc_id, text=by_id.get(doc_id, ""), score=score)
        for doc_id, score in scored
    ]
    return contextual_compress(
        hits, max_chars=max_chars, enabled=cfg.contextual_compression
    )


ABLATION_NOTE = (
    "Enable CRE_RAG_PARITY_MODERN_RERANK on staging only after measuring "
    "≥+3 pts vs baseline with wrong-auto-link rate flat "
    "(see scripts/evaluate_librarian.py / score_b2_hop_distance.py)."
)
