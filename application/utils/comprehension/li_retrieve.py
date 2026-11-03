"""LlamaIndex-backed fusion over existing pgvector/SQL rankings (not a second SoT).

When LI is unavailable, callers fall back to ``extras.rrf``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_LI_WARNED = False


def li_available() -> bool:
    try:
        from llama_index.core.retrievers.fusion_retriever import (  # noqa: F401
            QueryFusionRetriever,
        )

        return True
    except Exception:  # noqa: BLE001
        return False


def _warn_once(msg: str) -> None:
    global _LI_WARNED
    if not _LI_WARNED:
        logger.warning(msg)
        _LI_WARNED = True


def fuse_rankings_with_llamaindex(
    rankings: Sequence[Sequence[T]],
    *,
    key: Callable[[T], str],
) -> Optional[List[T]]:
    """Run LlamaIndex ``QueryFusionRetriever._reciprocal_rerank_fusion`` on hits.

    Returns ``None`` when LI cannot be imported or fusion fails so callers keep
    the hand-rolled ``extras.rrf`` path.
    """
    if not rankings:
        return []
    try:
        from llama_index.core.schema import NodeWithScore, TextNode
        from llama_index.core.retrievers.fusion_retriever import QueryFusionRetriever
    except Exception:  # noqa: BLE001
        _warn_once(
            "LlamaIndex unavailable for OWASP_CX_LI_RETRIEVE/HYBRID fusion; "
            "falling back to hand-rolled RRF"
        )
        return None

    # Call LI's RRF implementation without constructing QueryFusionRetriever
    # (that ctor pulls llama-index-llms-openai for query rewrite).
    by_key: dict[str, T] = {}
    results: dict = {}
    for i, ranking in enumerate(rankings):
        nodes: List[NodeWithScore] = []
        for hit in ranking:
            k = key(hit)
            by_key.setdefault(k, hit)
            score = float(getattr(hit, "score", 0.0) or 0.0)
            node = TextNode(id_=k, text=k)
            nodes.append(NodeWithScore(node=node, score=score))
        results[("q", i)] = nodes

    try:
        fused_nodes = QueryFusionRetriever._reciprocal_rerank_fusion(
            object(), results  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001
        _warn_once("LI reciprocal fusion failed; falling back to hand-rolled RRF")
        return None

    out: List[T] = []
    for nws in fused_nodes:
        k = getattr(nws.node, "id_", None) or getattr(nws.node, "node_id", None)
        if k is None:
            continue
        hit = by_key.get(str(k))
        if hit is None:
            continue
        try:
            hit.score = float(nws.score or 0.0)
        except Exception:  # noqa: BLE001
            pass
        out.append(hit)
    return out
