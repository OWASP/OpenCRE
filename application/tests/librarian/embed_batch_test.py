"""Query-embedding batch cache for Module C retrieval.

Hermetic: no Gemini calls. The cache must collapse the repeated header/body
embeds that prior-caged dual-index retrieval makes for one chunk, and prefetch
a queue batch in as few list calls as the batch size allows.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import unittest
from datetime import datetime, timezone
from typing import Dict, List
from unittest import mock

from application.utils.librarian.candidate_retriever import (
    CandidatePool,
    CandidateRetriever,
)
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.dual_index_retriever import DualIndexRetriever
from application.utils.librarian.embed_batch import (
    QueryEmbedCache,
    install_query_embed_cache,
    prefetch_retriever_embeddings,
)
from application.utils.librarian.pipeline import LibrarianPipeline
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.schemas import CreCandidate, KnowledgeQueueItem

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN = "run-embed-batch"

HUB = {
    "111-111": [1.0, 0.0, 0.0],
    "222-222": [0.0, 1.0, 0.0],
}


class _CountingEmbed:
    def __init__(self) -> None:
        self.calls: List[object] = []
        self._vectors: Dict[str, List[float]] = {
            "header": [1.0, 0.0, 0.0],
            "body text": [0.0, 1.0, 0.0],
            "Section: Access control\n\nbody text": [1.0, 0.0, 0.0],
            "Section: Access control": [1.0, 0.0, 0.0],
            "plain": [1.0, 0.0, 0.0],
        }

    def __call__(self, text):
        self.calls.append(text)
        if isinstance(text, list):
            return [list(self._vectors[t]) for t in text]
        return list(self._vectors[text])


class QueryEmbedCacheTest(unittest.TestCase):
    def test_prefetch_uses_one_list_call_and_then_hits_memory(self) -> None:
        embed = _CountingEmbed()
        cache = QueryEmbedCache(embed, batch_size=8)
        n = cache.prefetch(["header", "body text", "header", ""])
        self.assertEqual(n, 2)
        self.assertEqual(embed.calls, [["header", "body text"]])
        self.assertEqual(cache("header"), [1.0, 0.0, 0.0])
        self.assertEqual(cache("body text"), [0.0, 1.0, 0.0])
        self.assertEqual(len(embed.calls), 1)

    def test_prefetch_chunks_at_batch_size(self) -> None:
        embed = _CountingEmbed()
        embed._vectors.update({str(i): [1.0, 0.0, 0.0] for i in range(5)})
        cache = QueryEmbedCache(embed, batch_size=2)
        cache.prefetch([str(i) for i in range(5)])
        self.assertEqual(embed.calls, [["0", "1"], ["2", "3"], ["4"]])

    def test_list_unsupported_falls_back_to_single_calls(self) -> None:
        def single_only(text: str) -> List[float]:
            if isinstance(text, list):
                raise TypeError("no batch")
            return [1.0, 0.0, 0.0]

        cache = QueryEmbedCache(single_only, batch_size=4)
        self.assertEqual(cache.prefetch(["a", "b"]), 2)
        self.assertEqual(cache("a"), [1.0, 0.0, 0.0])


class InstallCacheTest(unittest.TestCase):
    def test_install_wraps_nested_retrievers_once(self) -> None:
        embed = _CountingEmbed()
        pool = CandidatePool.from_mapping(HUB)
        name = CandidateRetriever(embed_fn=embed, pool=pool, top_k=2, threshold=0.0)
        summary = CandidateRetriever(embed_fn=embed, pool=pool, top_k=2, threshold=0.0)
        dual = DualIndexRetriever(name, summary, top_k=2, threshold=0.0)
        # Prior cage disabled so retrieve is a single inner call; we only check wiring.
        root = PriorCagedRetriever(dual, CrePriorIndex.empty(), enabled=False)
        cache = install_query_embed_cache(root)
        self.assertIsNotNone(cache)
        self.assertIs(name._embed_fn, cache)
        self.assertIs(summary._embed_fn, cache)
        cache.prefetch(["Section: Access control", "body text"])
        dual.retrieve("Section: Access control\n\nbody text")
        self.assertEqual(embed.calls, [["Section: Access control", "body text"]])


class PipelinePrefetchTest(unittest.TestCase):
    def test_pipeline_prefetches_before_retrieve(self) -> None:
        embed = _CountingEmbed()
        pool = CandidatePool.from_mapping(HUB)
        retriever = CandidateRetriever(
            embed_fn=embed, pool=pool, top_k=1, threshold=0.0
        )

        class _Reranker:
            def rerank(self, text, audit):
                return audit.model_copy(
                    update={
                        "reranked": [CreCandidate(cre_id="111-111", score_rerank=2.0)]
                    }
                )

        class _Scaler:
            def confidence(self, logits):
                return 0.99

        class _Source:
            def items(self):
                return [
                    _row("plain", "1"),
                    _row("plain", "2"),
                ]

        pipeline = LibrarianPipeline(
            _Source(),
            retriever,
            _Reranker(),
            _Scaler(),
            threshold=0.8,
            pipeline_run_id=RUN,
            known_cre_ids=frozenset({"111-111"}),
        )
        with mock.patch.dict(os.environ, {"CRE_LIBRARIAN_EMBED_BATCH": "1"}):
            result = pipeline.run(at=AT)
        self.assertEqual(result.stats.total, 2)
        self.assertEqual(embed.calls, [["plain"]])

    def test_disabled_keeps_per_call_embeds(self) -> None:
        embed = _CountingEmbed()
        with mock.patch.dict(os.environ, {"CRE_LIBRARIAN_EMBED_BATCH": "0"}):
            n = prefetch_retriever_embeddings(
                CandidateRetriever(
                    embed_fn=embed,
                    pool=CandidatePool.from_mapping(HUB),
                    top_k=1,
                    threshold=0.0,
                ),
                ["plain", "plain"],
            )
        self.assertEqual(n, 0)
        self.assertEqual(embed.calls, [])


def _row(text: str, row_id: str) -> KnowledgeQueueItem:
    return KnowledgeQueueItem(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:{row_id}",
        artifact_id="art:owasp/x:a.md",
        pipeline_run_id=RUN,
        schema_version="0.2.0",
        source_type="github",
        source_repo="owasp/x",
        source_commit_sha="abcdef1",
        locator_kind="repo_path",
        locator_path="a.md",
        span_index=0,
        span_total=1,
        text=text,
        confidence=0.9,
        llm_label="KNOWLEDGE",
        created_at="2026-01-01T00:00:00Z",
    )
