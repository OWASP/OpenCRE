"""Header → name stubs, body → summaries, unioned C.1 shortlist."""

from __future__ import annotations

import unittest

from application.utils.librarian.dual_index_retriever import DualIndexRetriever
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


class _RecordingRetriever:
    def __init__(self, hits: list[tuple[str, float]]) -> None:
        self.hits = hits
        self.texts: list[str] = []
        self.allowlists: list[object] = []

    def retrieve(self, text: str, *, allowlist=None) -> RetrievalAudit:
        self.texts.append(text)
        self.allowlists.append(allowlist)
        return RetrievalAudit(
            retriever="rec",
            candidates=[
                CreCandidate(cre_id=cid, score_vector=score) for cid, score in self.hits
            ],
            reranked=[],
            threshold=0.8,
        )


_A01 = (
    "Source: A01\n"
    "Section: Broken Access Control\n"
    "Section-ID: A01\n"
    "\n"
    "Long narrative about IDOR and missing authorization checks.\n"
)


class DualIndexRetrieverTest(unittest.TestCase):
    def test_header_hits_name_pool_body_hits_summary_pool(self) -> None:
        names = _RecordingRetriever([("724-770", 0.91)])
        summaries = _RecordingRetriever([("166-151", 0.95)])
        retriever = DualIndexRetriever(names, summaries, top_k=20, threshold=0.8)
        audit = retriever.retrieve(_A01)
        self.assertEqual(len(names.texts), 1)
        self.assertEqual(len(summaries.texts), 1)
        self.assertIn("Broken Access Control", names.texts[0])
        self.assertNotIn("IDOR", names.texts[0])
        self.assertIn("IDOR", summaries.texts[0])
        self.assertNotIn("Section: Broken Access Control", summaries.texts[0])
        ids = [c.cre_id for c in audit.candidates]
        self.assertIn("166-151", ids)
        self.assertIn("724-770", ids)
        self.assertIn("dual-index", audit.retriever)

    def test_empty_header_skips_name_pool(self) -> None:
        names = _RecordingRetriever([("should-not-appear", 0.99)])
        summaries = _RecordingRetriever([("111-111", 0.8)])
        retriever = DualIndexRetriever(names, summaries, top_k=20, threshold=0.8)
        audit = retriever.retrieve("just a paragraph about passwords\n")
        self.assertEqual(names.texts, [])
        self.assertEqual(summaries.texts, ["just a paragraph about passwords"])
        self.assertEqual([c.cre_id for c in audit.candidates], ["111-111"])

    def test_union_keeps_higher_score_and_respects_top_k(self) -> None:
        names = _RecordingRetriever([("aaa", 0.5), ("bbb", 0.4)])
        summaries = _RecordingRetriever([("aaa", 0.9), ("ccc", 0.8)])
        retriever = DualIndexRetriever(names, summaries, top_k=2, threshold=0.8)
        audit = retriever.retrieve(_A01)
        ids = [c.cre_id for c in audit.candidates]
        self.assertIn("aaa", ids)
        self.assertAlmostEqual(
            next(c.score_vector or 0 for c in audit.candidates if c.cre_id == "aaa"),
            0.9,
        )
        self.assertEqual(len(ids), 2)

    def test_name_hits_are_reserved_when_summaries_score_higher(self) -> None:
        names = _RecordingRetriever([("724-770", 0.50)])
        summaries = _RecordingRetriever(
            [(f"s{i:03d}", 0.99 - i * 0.001) for i in range(8)]
        )
        retriever = DualIndexRetriever(names, summaries, top_k=4, threshold=0.8)
        audit = retriever.retrieve(_A01)
        ids = [c.cre_id for c in audit.candidates]
        self.assertIn("724-770", ids)
        self.assertEqual(len(ids), 4)

    def test_allowlist_is_forwarded(self) -> None:
        names = _RecordingRetriever([("724-770", 0.9)])
        summaries = _RecordingRetriever([("166-151", 0.9)])
        retriever = DualIndexRetriever(names, summaries, top_k=20, threshold=0.8)
        allowed = frozenset({"724-770", "166-151"})
        retriever.retrieve(_A01, allowlist=allowed)
        self.assertEqual(names.allowlists[0], allowed)
        self.assertEqual(summaries.allowlists[0], allowed)


if __name__ == "__main__":
    unittest.main()
