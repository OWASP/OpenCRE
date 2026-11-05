"""Phase 3: hybrid RRF retrieve, LC router strangler, citations, decide node."""

import unittest

from application.utils.librarian.schemas import Decision
from application.utils.rag_parity.flags import RagParityFlags
from application.utils.rag_parity.phase3_citations import (
    strip_uncited_sentences,
    synthesize_cited_answer,
)
from application.utils.rag_parity.phase3_decide_node import (
    attach_decide_node,
    opencre_decide_node,
)
from application.utils.rag_parity.phase3_retrieve import (
    hybrid_retrieve,
    reciprocal_rank_fusion,
)
from application.utils.rag_parity.phase3_router import route


class RrfTest(unittest.TestCase):
    def test_fusion_prefers_shared_top(self) -> None:
        a = [("cre-a", 0.9), ("cre-b", 0.8)]
        b = [("cre-b", 0.95), ("cre-c", 0.7)]
        fused = reciprocal_rank_fusion([a, b], k=60)
        self.assertEqual(fused[0][0], "cre-b")


class HybridRetrieveTest(unittest.TestCase):
    def test_multi_query_and_filter(self) -> None:
        def searcher(q: str, top_k: int):
            if "password" in q.lower():
                return [("111", 0.9), ("222", 0.5)][:top_k]
            return [("222", 0.8), ("333", 0.4)][:top_k]

        hits = hybrid_retrieve(
            "password length",
            searcher,
            expander=lambda q: [q, "credential length"],
            allowed_cre_ids=["111", "222"],
        )
        ids = [h.cre_id for h in hits]
        self.assertIn("111", ids)
        self.assertIn("222", ids)
        self.assertNotIn("333", ids)


class RouterTest(unittest.TestCase):
    def test_regex_path_when_flag_off(self) -> None:
        d = route("ASVS section V2.1.1", flags=RagParityFlags(lc_router=False))
        self.assertEqual(d.tool, "map_standard_section")
        self.assertEqual(d.backend, "regex")

    def test_lc_path_uses_injected_router(self) -> None:
        d = route(
            "anything",
            flags=RagParityFlags(lc_router=True),
            llm_router=lambda _t, _tools: "retrieve_cre",
        )
        self.assertEqual(d.tool, "retrieve_cre")
        self.assertEqual(d.backend, "langchain")


class CitationsTest(unittest.TestCase):
    def test_strips_uncited(self) -> None:
        draft = "Passwords must be long [1]. Uncited fluff here. Also CRE:#111."
        cleaned = strip_uncited_sentences(draft)
        self.assertIn("[1]", cleaned)
        self.assertNotIn("Uncited fluff", cleaned)

    def test_preserves_end_cite_style_prose(self) -> None:
        # synthesize SYSTEM asks models to end with [n] — do not reduce to markers only.
        draft = (
            "The OWASP SAMM is an open framework to improve software security. "
            "It is technology and process agnostic. [1][3]"
        )
        cleaned = strip_uncited_sentences(draft)
        self.assertIn("OWASP SAMM", cleaned)
        self.assertIn("agnostic", cleaned)
        self.assertIn("[1]", cleaned)

    def test_cite_only_result_falls_back_to_draft(self) -> None:
        draft = "Substantial prose about ASVS without inline markers. [2]"
        cleaned = synthesize_cited_answer(draft, enabled=True)
        self.assertIn("Substantial prose", cleaned)
        self.assertNotEqual(cleaned.strip(), "[2]")

    def test_flag_off_passthrough(self) -> None:
        draft = "No cites at all."
        self.assertEqual(synthesize_cited_answer(draft, enabled=False), draft)


class DecideNodeTest(unittest.TestCase):
    def test_calls_opencre_decide_not_framework_policy(self) -> None:
        out = opencre_decide_node(
            {
                "confidence": 0.9,
                "threshold": 0.8,
                "candidate_cre_ids": ["111-111"],
            }
        )
        self.assertEqual(out["policy"], "opencre.decide")
        self.assertEqual(out["decision"], Decision.linked.value)
        self.assertEqual(out["cre_ids"], ["111-111"])

    def test_below_tau_goes_review(self) -> None:
        out = opencre_decide_node(
            {
                "confidence": 0.5,
                "tau": 0.8,
                "candidate_cre_ids": ["111-111"],
            }
        )
        self.assertEqual(out["decision"], Decision.review.value)

    def test_attach_registers_node(self) -> None:
        g = attach_decide_node({})
        self.assertIn("opencre_decide", g["nodes"])


if __name__ == "__main__":
    unittest.main()
