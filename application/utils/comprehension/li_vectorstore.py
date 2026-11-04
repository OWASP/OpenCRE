"""LlamaIndex VectorStoreIndex over OpenCRE pgvector (Postgres remains SoT).

Read-only adapter: ``query`` runs the same dense SQL as ``retrieve._dense``.
No second embedding corpus, no LI disk index. Gated by ``OWASP_CX_LI_VSTORE`` /
``CRE_RAG_PARITY_LI_VSTORE`` (DEFAULT_ON since TASK-14.8; force off with ``=0``).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

logger = logging.getLogger(__name__)

_LI_WARNED = False


def li_vectorstore_available() -> bool:
    try:
        from llama_index.core import VectorStoreIndex  # noqa: F401
        from llama_index.core.vector_stores.types import (  # noqa: F401
            BasePydanticVectorStore,
        )

        return True
    except Exception:  # noqa: BLE001
        return False


def _warn_once(msg: str) -> None:
    global _LI_WARNED
    if not _LI_WARNED:
        logger.warning(msg)
        _LI_WARNED = True


def fetch_hits_via_vectorstore(
    *,
    conn: Any,
    texts: Sequence[str],
    embed_many: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    limit: int,
    where_sql: str,
) -> Optional[List[Any]]:
    """Retrieve ``LaneHit``s via public ``VectorStoreIndex`` over OpenCRE pgvector.

    Returns ``None`` when LI is unavailable or retrieve fails so callers keep the
    hand / QueryFusion path.
    """
    if not texts:
        return []
    try:
        from llama_index.core import VectorStoreIndex
        from llama_index.core.base.embeddings.base import BaseEmbedding
        from llama_index.core.schema import TextNode
        from llama_index.core.vector_stores.types import (
            BasePydanticVectorStore,
            VectorStoreQuery,
            VectorStoreQueryResult,
        )
    except Exception:  # noqa: BLE001
        _warn_once(
            "LlamaIndex unavailable for OWASP_CX_LI_VSTORE; "
            "falling back to hand dense retrieve"
        )
        return None

    from application.database.pgvector_utils import to_pgvector_literal
    from application.utils.comprehension.retrieve import _dense
    from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, LaneHit

    class _OpenCREPgVectorStore(BasePydanticVectorStore):
        """Read-only view of the existing ``embeddings`` table."""

        stores_text: bool = True
        is_embedding_query: bool = True

        def __init__(self, connection: Any, where: str) -> None:
            super().__init__(stores_text=True, is_embedding_query=True)
            self._connection = connection
            self._where = where

        @property
        def client(self) -> Any:
            return self._connection

        def add(self, nodes: Sequence[Any], **kwargs: Any) -> List[str]:
            # Postgres embeddings table is the SoT — never write from LI.
            return []

        def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
            return None

        def query(
            self, query: VectorStoreQuery, **kwargs: Any
        ) -> VectorStoreQueryResult:
            emb = query.query_embedding
            top_k = int(query.similarity_top_k or limit or 10)
            if not emb:
                return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])
            hits = _dense(
                self._connection,
                to_pgvector_literal(list(emb)),
                self._where,
                top_k,
            )
            nodes: List[TextNode] = []
            sims: List[float] = []
            ids: List[str] = []
            for h in hits:
                url = str(h.url or "")
                node = TextNode(
                    id_=url or str(h.embedding_id or ""),
                    text=str(h.content or url),
                    metadata={
                        "url": url,
                        "embedding_id": str(h.embedding_id or ""),
                        "doc_type": str(h.doc_type or ""),
                        "channel": CHANNEL_AGENT,
                    },
                )
                nodes.append(node)
                sims.append(float(h.score or 0.0))
                ids.append(url)
            return VectorStoreQueryResult(nodes=nodes, similarities=sims, ids=ids)

    class _FnEmbedding(BaseEmbedding):
        """Wrap OpenCRE ``embed_many`` / get_text_embeddings."""

        def __init__(self, fn: Callable[[Sequence[str]], Sequence[Sequence[float]]]):
            super().__init__()
            self._fn = fn

        def _embed_one(self, text: str) -> List[float]:
            rows = self._fn([text])
            if not rows:
                return []
            return [float(x) for x in rows[0]]

        def _get_query_embedding(self, query: str) -> List[float]:
            return self._embed_one(query)

        def _get_text_embedding(self, text: str) -> List[float]:
            return self._embed_one(text)

        async def _aget_query_embedding(self, query: str) -> List[float]:
            return self._embed_one(query)

        async def _aget_text_embedding(self, text: str) -> List[float]:
            return self._embed_one(text)

    try:
        store = _OpenCREPgVectorStore(conn, where_sql)
        embed_model = _FnEmbedding(embed_many)
        index = VectorStoreIndex.from_vector_store(store, embed_model=embed_model)
        retriever = index.as_retriever(similarity_top_k=max(1, int(limit)))
    except Exception:  # noqa: BLE001
        _warn_once("LI VectorStoreIndex setup failed; falling back to hand dense")
        return None

    rankings: List[List[LaneHit]] = []
    try:
        for text in texts:
            if not text:
                continue
            nodes_with_scores = retriever.retrieve(text)
            hits: List[LaneHit] = []
            for nws in nodes_with_scores:
                node = nws.node
                meta = dict(getattr(node, "metadata", None) or {})
                url = str(meta.get("url") or getattr(node, "id_", "") or "")
                hits.append(
                    LaneHit(
                        channel=CHANNEL_AGENT,
                        score=float(nws.score or 0.0),
                        embedding_id=str(meta.get("embedding_id") or ""),
                        content=str(
                            getattr(node, "text", None) or meta.get("url") or ""
                        ),
                        url=url,
                        doc_type=str(meta.get("doc_type") or ""),
                    )
                )
            rankings.append(hits)
    except Exception:  # noqa: BLE001
        _warn_once("LI VectorStoreIndex retrieve failed; falling back to hand dense")
        return None

    if not rankings:
        return []
    if len(rankings) == 1:
        return rankings[0]

    # Multi-query: prefer public QueryFusion RRF when LI_RETRIEVE is also on.
    from application.utils.comprehension import flags
    from application.utils.comprehension.extras import rrf

    if flags.on("LI_RETRIEVE"):
        from application.utils.comprehension.li_retrieve import (
            fuse_rankings_with_llamaindex,
        )

        fused = fuse_rankings_with_llamaindex(rankings, key=lambda h: h.url)
        if fused is not None:
            return fused
    return rrf(rankings, key=lambda h: h.url)
