"""Hermetic tests for the live-report plumbing in ``scripts/evaluate_librarian.py``.

The live reports (recall/top-1, the C.3 ECE gate, the C.4 decision accuracy) only
run under ``--use_live_embeddings``, which needs a populated DB, an embedding
model, and the cross-encoder — so nothing exercised their wiring. That is exactly
the code that has to share one retrieve+rerank pass and one fitted ``T`` across
three reports, so the sharing is asserted here against stub seams instead:

- ``live_audits`` must call the pipeline once per row, never once per report.
- ``calibration_set`` must draw only the positive + hard_negative slices.
- ``report_calibration`` must hand back the fitted scaler, and must fail (status
  1, no scaler) on a degenerate set rather than reporting success.
- ``report_decision_accuracy`` must consume that scaler and the shared audits
  without touching the retriever or reranker again.
"""

import importlib.util
import os
import unittest
from typing import List, Optional

from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

# The harness is a standalone script, not an importable package module.
_HARNESS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "evaluate_librarian.py"
)
_spec = importlib.util.spec_from_file_location("evaluate_librarian", _HARNESS_PATH)
assert _spec and _spec.loader
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


def _golden_row(
    row_id: str,
    slice_name: str,
    text: str,
    cre_ids: List[str],
    reason_code: Optional[str] = None,
):
    """Build a GoldenDatasetRow through the real validator, not a stub.

    ``expected.decision`` is required by the schema, and ``linked`` requires
    ``cre_ids`` while ``review`` requires a ``reason_code``, so both are derived:
    rows with expected ids are linked, rows without route to review below the bar.
    """
    from application.utils.librarian.schemas import GoldenDatasetRow

    expected: dict = {
        "decision": "linked" if cre_ids else "review",
        "cre_ids": cre_ids or None,
    }
    if not cre_ids:
        expected["reason_code"] = reason_code or "BELOW_THRESHOLD"
    elif reason_code is not None:
        expected["reason_code"] = reason_code
    source_input: dict = {"text": text, "source_standard": "ASVS"}
    if slice_name == "explicit":
        # The schema ties the explicit slice to a cited CRE id.
        source_input["explicit_cre_ref"] = (cre_ids or ["616-305"])[0]
    return GoldenDatasetRow.model_validate(
        {
            "id": row_id,
            "schema_version": "0.1.0",
            "slice": slice_name,
            "input": source_input,
            "expected": expected,
            "provenance": {
                "section_path": f"{row_id}.md",
                "ground_truth_source": "synthesised for the harness plumbing tests",
            },
        }
    )


class CountingPipeline:
    """Stub retriever+reranker that records how many passes it was asked for."""

    def __init__(self, shortlists):
        # shortlists: row text -> list of (cre_id, logit), best first
        self._shortlists = shortlists
        self.retrieve_calls = 0
        self.rerank_calls = 0

    def retrieve(self, text: str) -> RetrievalAudit:
        self.retrieve_calls += 1
        pairs = self._shortlists.get(text, [])
        return RetrievalAudit(
            retriever="stub/1.0.0",
            candidates=[CreCandidate(cre_id=c, score_vector=0.5) for c, _ in pairs],
            reranked=[],
            threshold=0.0,
        )

    def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
        self.rerank_calls += 1
        pairs = self._shortlists.get(text, [])
        return audit.model_copy(
            update={
                "reranked": [
                    CreCandidate(cre_id=c, score_rerank=logit) for c, logit in pairs
                ]
            }
        )


class LiveAuditsTest(unittest.TestCase):
    def test_pipeline_runs_once_per_row_not_once_per_report(self) -> None:
        rows = [
            _golden_row("p1", "positive", "alpha", ["616-305"]),
            _golden_row("n1", "hard_negative", "beta", []),
        ]
        pipe = CountingPipeline(
            {"alpha": [("616-305", 4.0)], "beta": [("111-111", 3.0)]}
        )

        audits = harness.live_audits(rows, pipe, pipe)

        self.assertEqual(pipe.retrieve_calls, 2)
        self.assertEqual(pipe.rerank_calls, 2)
        self.assertEqual(set(audits), {"p1", "n1"})

        # Three reports read the same audits; none of them may re-run the pipeline.
        harness.report_retrieval_recall(rows, audits, 10, 5)
        _status, scaler = harness.report_calibration(rows, audits)
        self.assertIsNotNone(scaler)
        harness.report_decision_accuracy(rows, audits, scaler, 0.80)
        self.assertEqual(pipe.retrieve_calls, 2)
        self.assertEqual(pipe.rerank_calls, 2)


class CalibrationSetTest(unittest.TestCase):
    def test_draws_only_the_two_calibration_slices(self) -> None:
        rows = [
            _golden_row("p1", "positive", "alpha", ["616-305"]),
            _golden_row("n1", "hard_negative", "beta", []),
            _golden_row("a1", "ambiguous", "gamma", ["616-305"]),
            _golden_row("e1", "explicit", "delta", ["616-305"]),
        ]
        pipe = CountingPipeline(
            {
                "alpha": [("616-305", 4.0)],
                "beta": [("111-111", 3.0)],
                "gamma": [("616-305", 2.0)],
                "delta": [("616-305", 1.0)],
            }
        )
        audits = harness.live_audits(rows, pipe, pipe)

        logit_sets, labels = harness.calibration_set(rows, audits)

        # ambiguous/explicit rows are audited but must not enter the fit.
        self.assertEqual(len(logit_sets), 2)
        self.assertEqual(sorted(labels), [0.0, 1.0])

    def test_skips_rows_with_no_audit_and_empty_shortlists(self) -> None:
        rows = [
            _golden_row("p1", "positive", "alpha", ["616-305"]),
            _golden_row("p2", "positive", "empty", ["616-305"]),
            _golden_row("n1", "hard_negative", "beta", []),
        ]
        pipe = CountingPipeline(
            {"alpha": [("616-305", 4.0)], "beta": [("111-111", 3.0)]}
        )
        # "empty" yields no candidates; p3 is never audited at all.
        audits = harness.live_audits(rows, pipe, pipe)

        logit_sets, labels = harness.calibration_set(rows, audits)
        self.assertEqual(len(logit_sets), 2)
        self.assertEqual(len(labels), 2)


class ReportCalibrationTest(unittest.TestCase):
    def test_returns_status_and_fitted_scaler(self) -> None:
        rows = [
            _golden_row("p1", "positive", "alpha", ["616-305"]),
            _golden_row("p2", "positive", "alpha2", ["616-305"]),
            _golden_row("n1", "hard_negative", "beta", []),
            _golden_row("n2", "hard_negative", "beta2", []),
        ]
        pipe = CountingPipeline(
            {
                "alpha": [("616-305", 5.0), ("999-999", 0.1)],
                "alpha2": [("616-305", 4.0), ("999-999", 0.2)],
                "beta": [("111-111", 3.0), ("222-222", 2.9)],
                "beta2": [("111-111", 2.0), ("222-222", 1.9)],
            }
        )
        audits = harness.live_audits(rows, pipe, pipe)

        status, scaler = harness.report_calibration(rows, audits)

        self.assertIn(status, (0, 1))  # gate outcome depends on the stub logits
        self.assertIsNotNone(scaler)
        self.assertGreater(scaler.temperature, 0.0)

    def test_degenerate_set_fails_and_yields_no_scaler(self) -> None:
        # Single-class labels: every top-1 is correct, so T is unidentifiable.
        rows = [
            _golden_row("p1", "positive", "alpha", ["616-305"]),
            _golden_row("p2", "positive", "alpha2", ["616-305"]),
        ]
        pipe = CountingPipeline(
            {"alpha": [("616-305", 5.0)], "alpha2": [("616-305", 4.0)]}
        )
        audits = harness.live_audits(rows, pipe, pipe)

        status, scaler = harness.report_calibration(rows, audits)

        self.assertEqual(status, 1, "a skipped gate must not report success")
        self.assertIsNone(scaler)


class ReportDecisionAccuracyTest(unittest.TestCase):
    def test_grades_expected_decision_rows_off_shared_audits(self) -> None:
        from application.utils.librarian.calibration.temperature import (
            TemperatureScaler,
        )

        rows = [
            _golden_row("d1", "positive", "alpha", ["616-305"]),
            _golden_row(
                "d2", "hard_negative", "beta", [], reason_code="BELOW_THRESHOLD"
            ),
        ]
        pipe = CountingPipeline(
            {
                # A dominant top-1 clears tau; a near-tie falls below it.
                "alpha": [("616-305", 20.0), ("999-999", 0.0)],
                "beta": [("111-111", 1.0), ("222-222", 0.99)],
            }
        )
        audits = harness.live_audits(rows, pipe, pipe)
        before = (pipe.retrieve_calls, pipe.rerank_calls)

        status = harness.report_decision_accuracy(
            rows, audits, TemperatureScaler(1.0), 0.80
        )

        self.assertEqual(status, 0, "the C.4 report is informational, never a gate")
        self.assertEqual((pipe.retrieve_calls, pipe.rerank_calls), before)

    def test_no_graded_rows_is_not_an_error(self) -> None:
        from application.utils.librarian.calibration.temperature import (
            TemperatureScaler,
        )

        rows = [_golden_row("p1", "positive", "alpha", ["616-305"])]
        pipe = CountingPipeline({"alpha": [("616-305", 4.0)]})
        audits = harness.live_audits(rows, pipe, pipe)

        status = harness.report_decision_accuracy(
            rows, audits, TemperatureScaler(1.0), 0.80
        )
        self.assertEqual(status, 0)


if __name__ == "__main__":
    unittest.main()
