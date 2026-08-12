import time
import unittest

from application.defs.cheatsheet_defs import CheatsheetRecord
from application.utils.external_project_parsers.parsers.cheatsheet_rerank import (
    CandidateCRE,
    RerankError,
    build_rerank_graph,
    classify_confidence,
    rerank_candidates_with_llm,
)

# LangGraph's first StateGraph().compile() in a process pays a one-time
# lazy-import/compile cost (observed ~0.5s), unrelated to anything under
# test. Pay it here, at module load, so timing-sensitive assertions (e.g.
# test_llm_timeout_falls_back) measure only our own timeout mechanism, both
# in isolation and as part of the full suite.
build_rerank_graph()


def _record(**overrides) -> CheatsheetRecord:
    defaults = dict(
        source_id="Secrets_Management_Cheat_Sheet",
        title="Secrets Management Cheat Sheet",
        hyperlink="https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
        summary="Guidance on secure storage, rotation, and operational handling of secrets.",
        headings=["Introduction", "Architectural Patterns", "Secret Rotation"],
        raw_markdown_path="cheatsheets/Secrets_Management_Cheat_Sheet.md",
    )
    defaults.update(overrides)
    return CheatsheetRecord(**defaults)


def _candidates():
    return [
        CandidateCRE(
            cre_id="623-550", score=0.62, text="Operational secret rotation controls."
        ),
        CandidateCRE(cre_id="123-456", score=0.40, text="Unrelated logging guidance."),
    ]


class ClassifyConfidenceTest(unittest.TestCase):
    def test_high(self):
        self.assertEqual(classify_confidence(0.9), "high")
        self.assertEqual(classify_confidence(0.85), "high")

    def test_medium(self):
        self.assertEqual(classify_confidence(0.7), "medium")
        self.assertEqual(classify_confidence(0.84), "medium")

    def test_low(self):
        self.assertEqual(classify_confidence(0.0), "low")
        self.assertEqual(classify_confidence(0.69), "low")

    def test_out_of_range_raises(self):
        with self.assertRaises(RerankError):
            classify_confidence(1.5)
        with self.assertRaises(RerankError):
            classify_confidence(-0.1)

    def test_non_numeric_raises(self):
        with self.assertRaises(RerankError):
            classify_confidence("high")  # type: ignore[arg-type]


class RerankCandidatesWithLlmTest(unittest.TestCase):
    def test_empty_candidates_returns_empty(self):
        self.assertEqual(rerank_candidates_with_llm(_record(), []), [])

    def test_invalid_top_n_raises(self):
        with self.assertRaises(RerankError):
            rerank_candidates_with_llm(_record(), _candidates(), top_n=0)

    def test_successful_rerank_produces_reason_and_confidence(self):
        def stub(system, user, *, model):
            self.assertIn("CHEATSHEET_TITLE", user)
            self.assertIn("623-550", user)
            return {
                "ranked": [
                    {
                        "cre_id": "623-550",
                        "score": 0.91,
                        "reason": "Directly covers rotation.",
                    },
                    {"cre_id": "123-456", "score": 0.2, "reason": "Off-topic."},
                ]
            }

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=stub, top_n=5
        )
        self.assertEqual(len(results), 2)
        top = results[0]
        self.assertEqual(top.cre_id, "623-550")
        self.assertEqual(top.confidence, "high")
        self.assertFalse(top.needs_review)
        self.assertFalse(top.trace.fallback_used)
        self.assertEqual(top.trace.prompt_version, "v1")
        self.assertIn("rotation", top.reason.lower())
        self.assertEqual(results[1].confidence, "low")
        self.assertTrue(results[1].needs_review)

    def test_top_n_truncates_and_sorts_descending(self):
        def stub(system, user, *, model):
            return {
                "ranked": [
                    {"cre_id": "623-550", "score": 0.3, "reason": "r1"},
                    {"cre_id": "123-456", "score": 0.95, "reason": "r2"},
                ]
            }

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=stub, top_n=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].cre_id, "123-456")

    def test_hallucinated_cre_id_is_dropped(self):
        def stub(system, user, *, model):
            return {
                "ranked": [
                    {"cre_id": "623-550", "score": 0.9, "reason": "ok"},
                    {"cre_id": "999-999", "score": 0.99, "reason": "invented"},
                ]
            }

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=stub, top_n=5
        )
        by_id = {r.cre_id: r for r in results}
        self.assertNotIn("999-999", by_id)
        # the un-scored real candidate still gets a retrieval-only entry,
        # and must always be flagged for review since it was never actually
        # judged by the reranker (regardless of its confidence band).
        self.assertIn("123-456", by_id)
        self.assertTrue(by_id["123-456"].needs_review)

    def test_llm_exception_falls_back_to_retrieval_score(self):
        def stub(system, user, *, model):
            raise RuntimeError("provider unavailable")

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=stub, top_n=5
        )
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r.trace.fallback_used)
            self.assertIsNotNone(r.trace.fallback_reason)
            self.assertTrue(r.needs_review)
        # retrieval ordering preserved (0.62 > 0.40)
        self.assertEqual(results[0].cre_id, "623-550")

    def test_llm_timeout_falls_back(self):
        def slow_stub(system, user, *, model):
            time.sleep(0.2)
            return {"ranked": []}

        started = time.monotonic()
        results = rerank_candidates_with_llm(
            _record(),
            _candidates(),
            llm_score_fn=slow_stub,
            top_n=5,
            timeout_seconds=0.01,
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.15)  # well under the 0.2s stub delay
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.trace.fallback_used for r in results))

    def test_malformed_json_falls_back(self):
        def bad_stub(system, user, *, model):
            return {"not_ranked_key": []}

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=bad_stub, top_n=5
        )
        self.assertTrue(all(r.trace.fallback_used for r in results))

    def test_llm_returns_no_valid_candidates_falls_back(self):
        def empty_stub(system, user, *, model):
            return {
                "ranked": [{"cre_id": "not-a-real-id", "score": 0.5, "reason": "x"}]
            }

        results = rerank_candidates_with_llm(
            _record(), _candidates(), llm_score_fn=empty_stub, top_n=5
        )
        self.assertTrue(all(r.trace.fallback_used for r in results))


class RerankGraphIntegrationTest(unittest.TestCase):
    """End-to-end execution of the compiled LangGraph flow (RFC Issue E, Checkpoint E5)."""

    def test_graph_runs_success_path(self):
        app = build_rerank_graph()

        def stub(system, user, *, model):
            return {"ranked": [{"cre_id": "623-550", "score": 0.88, "reason": "match"}]}

        state = app.invoke(
            {
                "record": _record(),
                "candidates": [_candidates()[0]],
                "top_n": 5,
                "llm_score_fn": stub,
                "model_name": "test-model",
                "timeout_seconds": 5.0,
                "generated_at": "2026-08-13T00:00:00+00:00",
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        self.assertEqual(len(state["ranked"]), 1)
        self.assertEqual(state["ranked"][0].confidence, "high")

    def test_graph_runs_fallback_path(self):
        app = build_rerank_graph()

        def failing_stub(system, user, *, model):
            raise RuntimeError("boom")

        state = app.invoke(
            {
                "record": _record(),
                "candidates": _candidates(),
                "top_n": 5,
                "llm_score_fn": failing_stub,
                "model_name": "test-model",
                "timeout_seconds": 5.0,
                "generated_at": "2026-08-13T00:00:00+00:00",
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        self.assertEqual(len(state["ranked"]), 2)
        self.assertTrue(all(r.trace.fallback_used for r in state["ranked"]))


if __name__ == "__main__":
    unittest.main()
