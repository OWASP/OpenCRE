"""Hermetic tests for the C.0->C.4 pipeline (Week 6b).

Every stage is a trivial stub — no DB, embedding model, or cross-encoder.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from datetime import datetime, timezone

from application.utils.librarian.pipeline import LibrarianPipeline
from application.utils.librarian.schemas import (
    CreCandidate,
    KnowledgeQueueItem,
    LinkProposal,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
)

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN = "run-7"


def _row(text="Verify the JWT signature.", label="KNOWLEDGE", row_id="1"):
    return KnowledgeQueueItem(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:art:owasp/x:a.md:{row_id}",
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
        llm_label=label,
        created_at="2026-01-01T00:00:00Z",
    )


class _Source:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return iter(self._rows)


class _Retriever:
    def retrieve(self, text):
        return RetrievalAudit(
            retriever="stub",
            candidates=[CreCandidate(cre_id="616-305")],
            reranked=[],
            threshold=0.8,
        )


class _Reranker:
    def __init__(self, reranked):
        self._reranked = reranked

    def rerank(self, text, audit):
        return audit.model_copy(update={"reranked": list(self._reranked)})


class _Scaler:
    def __init__(self, conf):
        self._conf = conf

    def confidence(self, logits):
        return self._conf


TOP = [CreCandidate(cre_id="616-305", score_rerank=1.5)]


def _pipeline(rows, reranked, conf):
    return LibrarianPipeline(
        _Source(rows),
        _Retriever(),
        _Reranker(reranked),
        _Scaler(conf),
        threshold=0.8,
        pipeline_run_id=RUN,
    )


class PipelineTest(unittest.TestCase):
    def test_confident_row_auto_links(self):
        result = _pipeline([_row()], TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.linked, 1)
        self.assertEqual(result.stats.review, 0)
        self.assertIsInstance(result.envelopes[0], LinkProposal)
        self.assertEqual(result.envelopes[0].pipeline_run_id, RUN)

    def test_low_confidence_row_reviews_below_threshold(self):
        result = _pipeline([_row()], TOP, 0.4).run(at=AT)
        self.assertEqual(result.stats.review, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.below_threshold)

    def test_empty_shortlist_reviews_no_candidates(self):
        # Retriever also returns nothing — true empty shortlist.
        class EmptyRetriever:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub", candidates=[], reranked=[], threshold=0.8
                )

        pipeline = LibrarianPipeline(
            _Source([_row()]),
            EmptyRetriever(),
            _Reranker([]),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
        )
        env = pipeline.run(at=AT).envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        # Empty cage → CRE_GAP (coverage proposal), not a silent no_candidates.
        self.assertIn(env.reason_code, (ReasonCode.no_candidates, ReasonCode.cre_gap))

    def test_uncertain_row_is_skipped_at_boundary(self):
        result = _pipeline([_row(label="NOISE")], TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.skipped, 1)
        self.assertEqual(result.stats.total, 1)
        self.assertEqual(result.envelopes, [])

    def test_mixed_batch_counts(self):
        rows = [_row(), _row(label="NOISE"), _row()]
        result = _pipeline(rows, TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.total, 3)
        self.assertEqual(result.stats.linked, 2)
        self.assertEqual(result.stats.skipped, 1)
        self.assertEqual(result.stats.errored, 0)
        self.assertEqual(len(result.envelopes), 2)

    def test_authoritative_opencre_url_skips_retrieval(self):
        class BoomRetriever:
            def retrieve(self, text):
                raise AssertionError("retrieval must not run for authoritative URLs")

        text = "See https://opencre.org/cre/616-305 for MFA."
        pipeline = LibrarianPipeline(
            _Source([_row(text=text)]),
            BoomRetriever(),
            _Reranker(TOP),
            _Scaler(0.1),
            threshold=0.8,
            pipeline_run_id=RUN,
            known_cre_ids=frozenset({"616-305"}),
            cre_id_map={"616-305": "uuid-616"},
            cre_membership=frozenset({"uuid-616", "616-305"}),
        )
        result = pipeline.run(at=AT)
        self.assertEqual(result.stats.linked, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, LinkProposal)
        self.assertEqual(env.links[0].cre_id, "uuid-616")
        self.assertEqual(env.links[0].confidence, 1.0)
        self.assertEqual(env.retrieval.retriever, "explicit-link/0.1.0")

    def test_empty_retrieve_emits_cre_gap_with_proposal(self):
        class EmptyRetriever:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub+prior-cage/authentication:auth:empty",
                    candidates=[],
                    reranked=[],
                    threshold=0.8,
                )

        pipeline = LibrarianPipeline(
            _Source([_row(text="Section-ID: A07\nSection: Authentication Failures\n")]),
            EmptyRetriever(),
            _Reranker(TOP),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
            known_cre_ids=frozenset({"616-305", "177-260"}),
            cre_membership=frozenset({"616-305", "177-260"}),
        )
        result = pipeline.run(at=AT)
        self.assertEqual(result.stats.review, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.cre_gap)
        self.assertIsNotNone(env.suggested_links)
        self.assertEqual(len(env.suggested_links), 1)
        link = env.suggested_links[0]
        self.assertEqual(link.link_type, "Proposed new CRE")
        self.assertRegex(link.cre_id, r"^\d{3}-\d{3}$")
        self.assertNotIn(link.cre_id, {"616-305", "177-260"})
        self.assertIn("Authentication", link.rationale or "")


class PipelineCreMembershipGroundingTest(unittest.TestCase):
    """Emit-time guard: ghost cre_ids must not leave C on a LinkProposal."""

    def test_bogus_cre_id_cannot_produce_link_proposal(self):
        ghost = [CreCandidate(cre_id="not-a-real-cre", score_rerank=1.5)]
        pipeline = LibrarianPipeline(
            _Source([_row()]),
            _Retriever(),
            _Reranker(ghost),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
            cre_membership=frozenset({"616-305"}),
        )
        result = pipeline.run(at=AT)
        self.assertEqual(result.stats.linked, 0)
        self.assertEqual(result.stats.review, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.no_candidates)
        self.assertFalse(env.suggested_links)

    def test_valid_membership_still_auto_links(self):
        pipeline = LibrarianPipeline(
            _Source([_row()]),
            _Retriever(),
            _Reranker(TOP),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
            cre_membership=frozenset({"616-305"}),
        )
        result = pipeline.run(at=AT)
        self.assertEqual(result.stats.linked, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, LinkProposal)
        self.assertEqual(env.links[0].cre_id, "616-305")

    def test_review_suggested_links_drop_invalid_ids(self):
        mixed = [CreCandidate(cre_id="ghost-cre", score_rerank=0.2)]
        # Low confidence forces review; membership drops the ghost suggestion.
        # Vector union may still surface the retriever's valid 616-305 — that is
        # intentional (cosine top-2 must survive a bad CE pick).
        pipeline = LibrarianPipeline(
            _Source([_row()]),
            _Retriever(),
            _Reranker(mixed),
            _Scaler(0.4),
            threshold=0.8,
            pipeline_run_id=RUN,
            cre_membership=frozenset({"616-305"}),
        )
        result = pipeline.run(at=AT)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.below_threshold)
        self.assertEqual([lnk.cre_id for lnk in env.suggested_links], ["616-305"])
        self.assertNotIn("ghost-cre", [lnk.cre_id for lnk in env.suggested_links])


class PipelineErrorContainmentTest(unittest.TestCase):
    """A failing row must cost that row only, never the envelopes already built.

    These stages are stubs today but become live DB / embedding / cross-encoder
    calls in W8, so the containment is asserted at each seam that can raise.
    """

    def _run_with(self, failing_component, rows):
        """Build a pipeline whose one named component raises on every call."""
        parts = {
            "retriever": _Retriever(),
            "reranker": _Reranker(TOP),
            "scaler": _Scaler(0.95),
        }
        parts[failing_component] = failing_component_stub(failing_component)
        return LibrarianPipeline(
            _Source(rows),
            parts["retriever"],
            parts["reranker"],
            parts["scaler"],
            threshold=0.8,
            pipeline_run_id=RUN,
        ).run(at=AT)

    def test_retriever_failure_is_contained(self):
        result = self._run_with("retriever", [_row()])
        self.assertEqual(result.stats.errored, 1)
        self.assertEqual(result.stats.total, 1)
        self.assertEqual(result.envelopes, [])

    def test_reranker_failure_is_contained(self):
        result = self._run_with("reranker", [_row()])
        self.assertEqual(result.stats.errored, 1)
        self.assertEqual(result.envelopes, [])

    def test_scaler_failure_is_contained(self):
        result = self._run_with("scaler", [_row()])
        self.assertEqual(result.stats.errored, 1)
        self.assertEqual(result.envelopes, [])

    def test_one_bad_row_does_not_discard_the_good_ones(self):
        # The reranker fails only on the middle row's text.
        class _FlakyReranker:
            def rerank(self, text, audit):
                if "boom" in text:
                    raise RuntimeError("cross-encoder blew up on this pair")
                return audit.model_copy(update={"reranked": list(TOP)})

        rows = [_row(), _row(text="boom goes the model"), _row()]
        result = LibrarianPipeline(
            _Source(rows),
            _Retriever(),
            _FlakyReranker(),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
        ).run(at=AT)

        self.assertEqual(result.stats.total, 3)
        self.assertEqual(result.stats.errored, 1)
        self.assertEqual(result.stats.linked, 2)
        self.assertEqual(len(result.envelopes), 2)

    def test_errored_is_counted_separately_from_skipped(self):
        rows = [_row(label="NOISE"), _row()]
        result = self._run_with("retriever", rows)
        # The NOISE row is a clean boundary refusal; the other is a fault.
        self.assertEqual(result.stats.skipped, 1)
        self.assertEqual(result.stats.errored, 1)


class RowOutcomeTest(unittest.TestCase):
    """Per-row outcomes (W8): what the queue write-back keys its decision on.

    ``RunStats`` counts alone cannot say *which* rows finished, and retiring an
    errored row would silently drop that chunk from the pipeline forever.
    """

    def _run(self, rows, scaler_confidence=0.95):
        return LibrarianPipeline(
            _Source(rows),
            _Retriever(),
            _Reranker(TOP),
            _Scaler(scaler_confidence),
            threshold=0.8,
            pipeline_run_id=RUN,
        ).run(at=AT)

    def test_outcome_per_row_carries_the_queue_id(self):
        result = self._run([_row(row_id="a"), _row(row_id="b")])
        self.assertEqual([o.row_id for o in result.outcomes], ["a", "b"])
        self.assertEqual({o.status.value for o in result.outcomes}, {"linked"})

    def test_boundary_rejection_is_finished_with(self):
        """A malformed row cannot be fixed by re-reading it, so it counts as
        finished — otherwise it is re-read on every run, forever."""
        result = self._run([_row(row_id="bad", label="NOISE")])
        self.assertEqual([o.status.value for o in result.outcomes], ["skipped"])
        self.assertEqual(result.finished_row_ids(), ["bad"])

    def test_errored_row_is_not_finished(self):
        result = LibrarianPipeline(
            _Source([_row(row_id="a")]),
            failing_component_stub("retriever"),
            _Reranker(TOP),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
        ).run(at=AT)
        self.assertEqual([o.status.value for o in result.outcomes], ["errored"])
        self.assertEqual(result.finished_row_ids(), [])

    def test_finished_ids_mix_decisions_and_rejections_but_not_errors(self):
        rows = [_row(row_id="ok"), _row(row_id="skip", label="NOISE")]
        result = self._run(rows)
        self.assertEqual(sorted(result.finished_row_ids()), ["ok", "skip"])


class ShortlistJudgePipelineTest(unittest.TestCase):
    def test_judged_ids_lead_suggestions(self) -> None:
        """Lever C: Gemini shortlist picks prepend into preferred (lead=2)."""

        class MultiRetriever:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(
                            cre_id="noise-1", cre_name="Noise", score_vector=0.9
                        ),
                        CreCandidate(
                            cre_id="gold-a", cre_name="Gold A", score_vector=0.5
                        ),
                        CreCandidate(
                            cre_id="gold-b", cre_name="Gold B", score_vector=0.4
                        ),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        def llm(system: str, user: str) -> str:
            return '["gold-a", "gold-b"]'

        # Below τ → review keeps top-2 suggestions (auto-link stamps top-1 only).
        pipeline = LibrarianPipeline(
            _Source(
                [
                    _row(
                        text=(
                            "Standard: OWASP Top 10\n"
                            "Section-ID: A01\n"
                            "Section: Broken Access Control\n"
                        )
                    )
                ]
            ),
            MultiRetriever(),
            _Reranker(
                [
                    CreCandidate(cre_id="noise-1", score_rerank=2.0),
                    CreCandidate(cre_id="gold-a", score_rerank=0.1),
                    CreCandidate(cre_id="gold-b", score_rerank=0.05),
                ]
            ),
            _Scaler(0.4),
            threshold=0.8,
            pipeline_run_id=RUN,
            shortlist_llm_fn=llm,
        )
        result = pipeline.run(at=AT)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(
            [link.cre_id for link in (env.suggested_links or [])[:2]],
            ["gold-a", "gold-b"],
        )
        self.assertIn("shortlist-judge", env.retrieval.retriever)

    def test_judge_error_fail_open(self) -> None:
        def llm(system: str, user: str) -> str:
            raise RuntimeError("gemini down")

        result = LibrarianPipeline(
            _Source([_row()]),
            _Retriever(),
            _Reranker(TOP),
            _Scaler(0.95),
            threshold=0.8,
            pipeline_run_id=RUN,
            shortlist_llm_fn=llm,
        ).run(at=AT)
        self.assertEqual(result.stats.linked, 1)
        self.assertNotIn("shortlist-judge", result.envelopes[0].retrieval.retriever)


def failing_component_stub(kind):
    """A stub whose single method always raises, for the given seam."""

    class _Boom:
        def retrieve(self, text):
            raise RuntimeError("retriever down")

        def rerank(self, text, audit):
            raise RuntimeError("reranker down")

        def confidence(self, logits):
            raise RuntimeError("scaler down")

    assert kind in ("retriever", "reranker", "scaler")
    return _Boom()


if __name__ == "__main__":
    unittest.main()
