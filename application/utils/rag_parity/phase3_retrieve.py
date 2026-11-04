"""Phase 3: hybrid / RRF / multi-query retrieve over a pgvector-style adapter.

Does not replace pgvector as SoT — ranks ids returned by an injected searcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

Searcher = Callable[[str, int], Sequence[Tuple[str, float]]]
Expander = Callable[[str], Sequence[str]]


@dataclass(frozen=True)
class RetrieveHit:
    cre_id: str
    score: float
    sources: Tuple[str, ...]


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Tuple[str, float]]],
    *,
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Classic RRF: score = Σ 1/(k + rank). Higher is better."""
    scores: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (doc_id, _raw) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def expand_queries(query: str, expander: Optional[Expander] = None) -> List[str]:
    """Multi-query expand; default is identity + a light paraphrase stub."""
    base = (query or "").strip()
    if not base:
        return []
    if expander is not None:
        out = [base]
        for alt in expander(base):
            alt = (alt or "").strip()
            if alt and alt not in out:
                out.append(alt)
        return out
    return [base]


def metadata_filter_hits(
    hits: Sequence[RetrieveHit],
    *,
    allowed_cre_ids: Optional[Sequence[str]] = None,
    required_sources: Optional[Sequence[str]] = None,
) -> List[RetrieveHit]:
    allowed = set(allowed_cre_ids) if allowed_cre_ids is not None else None
    required = set(required_sources) if required_sources is not None else None
    out: List[RetrieveHit] = []
    for hit in hits:
        if allowed is not None and hit.cre_id not in allowed:
            continue
        if required is not None and not required.intersection(hit.sources):
            continue
        out.append(hit)
    return out


def hybrid_retrieve(
    query: str,
    searcher: Searcher,
    *,
    top_k: int = 20,
    expander: Optional[Expander] = None,
    rrf_k: int = 60,
    allowed_cre_ids: Optional[Sequence[str]] = None,
) -> List[RetrieveHit]:
    """Multi-query dense search fused with RRF; optional CRE id metadata filter."""
    queries = expand_queries(query, expander=expander)
    lists: List[Sequence[Tuple[str, float]]] = []
    source_map: Dict[str, List[str]] = {}
    for q in queries:
        ranked = list(searcher(q, top_k))
        lists.append(ranked)
        for cre_id, _ in ranked:
            source_map.setdefault(cre_id, []).append(q)
    fused = reciprocal_rank_fusion(lists, k=rrf_k)[:top_k]
    hits = [
        RetrieveHit(
            cre_id=cre_id,
            score=score,
            sources=tuple(source_map.get(cre_id, ())),
        )
        for cre_id, score in fused
    ]
    return metadata_filter_hits(hits, allowed_cre_ids=allowed_cre_ids)
