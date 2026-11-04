"""LlamaIndex public QueryFusion over existing pgvector/SQL rankings (not a second SoT).

Uses ``QueryFusionRetriever`` with ``FUSION_MODES.RECIPROCAL_RANK`` and
``num_queries=1`` (no LLM query rewrite). Prefetched dense/keyword lists are
exposed as tiny ``BaseRetriever`` adapters so we stay on the public API.

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
    """Fuse ranking lists via public ``QueryFusionRetriever`` (RRF mode).

    Returns ``None`` when LI cannot be imported or fusion fails so callers keep
    the hand-rolled ``extras.rrf`` path.
    """
    if not rankings:
        return []
    try:
        from llama_index.core.base.base_retriever import BaseRetriever
        from llama_index.core.llms import MockLLM
        from llama_index.core.retrievers.fusion_retriever import (
            FUSION_MODES,
            QueryFusionRetriever,
        )
        from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
    except Exception:  # noqa: BLE001
        _warn_once(
            "LlamaIndex unavailable for OWASP_CX_LI_RETRIEVE QueryFusion; "
            "falling back to hand-rolled RRF"
        )
        return None

    by_key: dict[str, T] = {}
    retrievers: List[Any] = []

    class _PrefetchedRetriever(BaseRetriever):
        """Returns a fixed hit list; ignores the query bundle (lists already fetched)."""

        def __init__(self, nodes: List[NodeWithScore]) -> None:
            super().__init__()
            self._nodes = nodes

        def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
            return list(self._nodes)

        async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
            return list(self._nodes)

    for ranking in rankings:
        nodes: List[NodeWithScore] = []
        for hit in ranking:
            k = key(hit)
            by_key.setdefault(k, hit)
            score = float(getattr(hit, "score", 0.0) or 0.0)
            # id_ + text = stable key so node.hash differs per URL and maps back.
            node = TextNode(id_=k, text=k)
            nodes.append(NodeWithScore(node=node, score=score))
        retrievers.append(_PrefetchedRetriever(nodes))

    if not retrievers:
        return []

    try:
        fusion = QueryFusionRetriever(
            retrievers=retrievers,
            llm=MockLLM(),
            mode=FUSION_MODES.RECIPROCAL_RANK,
            num_queries=1,  # no LLM query rewrite
            use_async=False,
            similarity_top_k=max(1, sum(len(r) for r in rankings)),
        )
        fused_nodes = fusion.retrieve(QueryBundle(query_str="__prefetched__"))
    except Exception:  # noqa: BLE001
        _warn_once("LI QueryFusionRetriever failed; falling back to hand-rolled RRF")
        return None

    out: List[T] = []
    seen: set[str] = set()
    for nws in fused_nodes:
        k = getattr(nws.node, "id_", None) or getattr(nws.node, "node_id", None)
        if k is None:
            continue
        ks = str(k)
        if ks in seen:
            continue
        hit = by_key.get(ks)
        if hit is None:
            continue
        seen.add(ks)
        try:
            setattr(hit, "score", float(nws.score or 0.0))
        except Exception:  # noqa: BLE001
            pass
        out.append(hit)
    return out
