import time
import unittest

from application.utils.external_project_parsers.parsers.cheatsheet_rerank import (
    RerankError,
    build_rationale_graph,
    classify_confidence,
    generate_link_rationale,
)

# LangGraph's first StateGraph().compile() in a process pays a one-time
# lazy-import/compile cost (observed ~0.5s), unrelated to anything under
# test. Pay it here, at module load, so timing-sensitive assertions (e.g.
# test_llm_timeout_falls_back) measure only our own timeout mechanism, both
# in isolation and as part of the full suite.
build_rationale_graph()


SECTION_TEXT = (
    "Secrets Management Cheat Sheet: guidance on secure storage, rotation, "
    "and operational handling of secrets."
)
CRE_ID = "623-550"
CRE_TEXT = "Operational secret rotation controls."


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


class GenerateLinkRationaleTest(unittest.TestCase):
    def test_empty_cre_id_raises(self):
        with self.assertRaises(RerankError):
            generate_link_rationale(SECTION_TEXT, "", CRE_TEXT, 0.9)

    def test_invalid_score_raises_before_llm_call(self):
        called = {"n": 0}

        def stub(system, user, *, model):
            called["n"] += 1
            return {"rationale": "x"}

        with self.assertRaises(RerankError):
            generate_link_rationale(
                SECTION_TEXT, CRE_ID, CRE_TEXT, 1.5, llm_rationale_fn=stub
            )
        self.assertEqual(called["n"], 0)

    def test_zero_timeout_seconds_raises(self):
        with self.assertRaises(RerankError):
            generate_link_rationale(
                SECTION_TEXT, CRE_ID, CRE_TEXT, 0.9, timeout_seconds=0
            )

    def test_infinite_timeout_seconds_raises(self):
        with self.assertRaises(RerankError):
            generate_link_rationale(
                SECTION_TEXT,
                CRE_ID,
                CRE_TEXT,
                0.9,
                timeout_seconds=float("inf"),
            )

    def test_boolean_timeout_seconds_raises(self):
        with self.assertRaises(RerankError):
            generate_link_rationale(
                SECTION_TEXT, CRE_ID, CRE_TEXT, 0.9, timeout_seconds=True
            )

    def test_successful_generation_produces_rationale_and_trace(self):
        def stub(system, user, *, model):
            self.assertIn("CHEATSHEET_TEXT", user)
            self.assertIn(CRE_ID, user)
            return {"rationale": "Both cover secret rotation controls directly."}

        result = generate_link_rationale(
            SECTION_TEXT, CRE_ID, CRE_TEXT, 0.91, llm_rationale_fn=stub
        )
        self.assertEqual(result.cre_id, CRE_ID)
        self.assertIn("rotation", result.rationale.lower())
        self.assertEqual(result.confidence, "high")
        self.assertFalse(result.fallback_used)
        self.assertFalse(result.trace.fallback_used)
        self.assertEqual(result.trace.prompt_version, "v2")
        self.assertIsNone(result.trace.fallback_reason)

    def test_llm_exception_falls_back_to_score_only_rationale(self):
        def stub(system, user, *, model):
            raise RuntimeError("provider unavailable")

        result = generate_link_rationale(
            SECTION_TEXT, CRE_ID, CRE_TEXT, 0.42, llm_rationale_fn=stub
        )
        self.assertTrue(result.fallback_used)
        self.assertTrue(result.trace.fallback_used)
        self.assertIsNotNone(result.trace.fallback_reason)
        self.assertIn("0.42", result.rationale)

    def test_llm_timeout_falls_back(self):
        def slow_stub(system, user, *, model):
            time.sleep(0.2)
            return {"rationale": "too slow"}

        started = time.monotonic()
        result = generate_link_rationale(
            SECTION_TEXT,
            CRE_ID,
            CRE_TEXT,
            0.6,
            llm_rationale_fn=slow_stub,
            timeout_seconds=0.01,
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.15)  # well under the 0.2s stub delay
        self.assertTrue(result.fallback_used)

    def test_malformed_json_falls_back(self):
        def bad_stub(system, user, *, model):
            return {"not_rationale_key": "x"}

        result = generate_link_rationale(
            SECTION_TEXT, CRE_ID, CRE_TEXT, 0.6, llm_rationale_fn=bad_stub
        )
        self.assertTrue(result.fallback_used)

    def test_empty_rationale_falls_back(self):
        def empty_stub(system, user, *, model):
            return {"rationale": ""}

        result = generate_link_rationale(
            SECTION_TEXT, CRE_ID, CRE_TEXT, 0.6, llm_rationale_fn=empty_stub
        )
        self.assertTrue(result.fallback_used)

    def test_missing_cre_text_still_produces_a_rationale(self):
        # cre_text may be empty (RFC's original CandidateCRE allowed this);
        # the prompt degrades gracefully rather than crashing.
        def stub(system, user, *, model):
            self.assertIn("<no text available>", user)
            return {"rationale": "Plausible match based on cheat sheet alone."}

        result = generate_link_rationale(
            SECTION_TEXT, CRE_ID, "", 0.75, llm_rationale_fn=stub
        )
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.confidence, "medium")


class RationaleGraphIntegrationTest(unittest.TestCase):
    """End-to-end execution of the compiled LangGraph flow."""

    def test_graph_runs_success_path(self):
        app = build_rationale_graph()

        def stub(system, user, *, model):
            return {"rationale": "match"}

        state = app.invoke(
            {
                "section_text": SECTION_TEXT,
                "cre_id": CRE_ID,
                "cre_text": CRE_TEXT,
                "score": 0.88,
                "llm_rationale_fn": stub,
                "model_name": "test-model",
                "timeout_seconds": 5.0,
                "generated_at": "2026-08-13T00:00:00+00:00",
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        self.assertEqual(state["result"].confidence, "high")
        self.assertFalse(state["result"].fallback_used)

    def test_graph_runs_fallback_path(self):
        app = build_rationale_graph()

        def failing_stub(system, user, *, model):
            raise RuntimeError("boom")

        state = app.invoke(
            {
                "section_text": SECTION_TEXT,
                "cre_id": CRE_ID,
                "cre_text": CRE_TEXT,
                "score": 0.3,
                "llm_rationale_fn": failing_stub,
                "model_name": "test-model",
                "timeout_seconds": 5.0,
                "generated_at": "2026-08-13T00:00:00+00:00",
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        self.assertTrue(state["result"].fallback_used)


if __name__ == "__main__":
    unittest.main()
