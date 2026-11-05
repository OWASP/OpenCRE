"""Phase 4: modern rerank + contextual compression."""

import unittest

from application.utils.rag_parity.flags import RagParityFlags
from application.utils.rag_parity.phase4_rerank import (
    ABLATION_NOTE,
    RerankHit,
    contextual_compress,
    rerank_and_compress,
)


class RerankCompressTest(unittest.TestCase):
    def test_injected_rerank_orders_by_score(self) -> None:
        def fake(query: str, docs):
            return [("b", 0.9), ("a", 0.1)]

        hits = rerank_and_compress(
            "q",
            [("a", "alpha text about passwords"), ("b", "beta text about MFA")],
            flags=RagParityFlags(modern_rerank=True, contextual_compression=False),
            rerank_fn=fake,
        )
        self.assertEqual([h.doc_id for h in hits], ["b", "a"])

    def test_compression_trims_to_budget(self) -> None:
        hits = [
            RerankHit("1", "A" * 100, 1.0),
            RerankHit("2", "B" * 100, 0.5),
        ]
        out = contextual_compress(hits, max_chars=120, enabled=True)
        total = sum(len(h.text) for h in out)
        self.assertLessEqual(total, 120)
        self.assertEqual(out[0].doc_id, "1")

    def test_ablation_note_present(self) -> None:
        self.assertIn("+3", ABLATION_NOTE)

    def test_owasp_cx_modern_rerank_alias_loads(self) -> None:
        import os
        from unittest import mock

        from application.utils.rag_parity.flags import load_flags

        with mock.patch.dict(os.environ, {"OWASP_CX_MODERN_RERANK": "1"}, clear=False):
            for k in ("CRE_RAG_PARITY_MODERN_RERANK",):
                os.environ.pop(k, None)
            self.assertTrue(load_flags().modern_rerank)


class RerankChainTest(unittest.TestCase):
    def _flags(self):
        from application.utils.rag_parity.flags import RagParityFlags

        return RagParityFlags(modern_rerank=True, contextual_compression=False)

    def test_falls_back_from_cohere_to_llm(self) -> None:
        from unittest import mock

        from application.utils.rag_parity import phase4_rerank as m

        docs = [("a", "x"), ("b", "y")]
        with mock.patch.object(
            m, "try_cohere_rerank", side_effect=RuntimeError
        ), mock.patch.object(
            m, "try_llm_rerank", return_value=[("b", 1.0), ("a", 0.5)]
        ):
            out = m.resolve_rerank_fn(self._flags())("q", docs)
        self.assertEqual([d for d, _ in out], ["b", "a"])

    def test_falls_back_to_identity_when_all_fail(self) -> None:
        from unittest import mock

        from application.utils.rag_parity import phase4_rerank as m

        docs = [("a", "x"), ("b", "y")]
        with mock.patch.object(
            m, "try_cohere_rerank", side_effect=RuntimeError
        ), mock.patch.object(m, "try_llm_rerank", side_effect=RuntimeError):
            out = m.resolve_rerank_fn(self._flags())("q", docs)
        self.assertEqual([d for d, _ in out], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
