"""Hermetic tests for C.4 envelope emitter (Week 6b). No key, DB, or model."""

import unittest
from datetime import datetime, timezone

from application.utils.librarian.decision_engine import DecisionResult
from application.utils.librarian.emitter import (
    AUTO_LINK_TYPE,
    SUGGESTED_LINK_TYPE,
    EmitterError,
    build_link_proposal,
    build_review_item,
    emit,
)
from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    CreCandidate,
    Decision,
    Locator,
    LocatorKind,
    ReasonCode,
    RetrievalAudit,
    SourceRef,
    SourceType,
)
from application.utils.librarian.section_validator import Section

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN = "run-42"


def _section() -> Section:
    return Section(
        chunk_id="chk:owasp/x@abcdef1:a.md",
        artifact_id="art:owasp/x:a.md",
        text="Verify the JWT signature before trusting the session.",
        title_hint=None,
        language="en",
        source=SourceRef(
            type=SourceType.github,
            repo="owasp/x",
            commit_sha="abcdef1",
            committed_at=AT,
        ),
        locator=Locator(kind=LocatorKind.repo_path, id="a.md", path="a.md"),
    )


def _audit() -> RetrievalAudit:
    return RetrievalAudit(
        retriever="retriever/0",
        candidates=[CreCandidate(cre_id="616-305")],
        reranked=[CreCandidate(cre_id="616-305", score_rerank=1.5)],
        threshold=0.8,
    )


LINKED = DecisionResult(Decision.linked, 0.91, ("616-305",), None)
REVIEW_LOW = DecisionResult(
    Decision.review, 0.42, ("616-305",), ReasonCode.below_threshold
)
REVIEW_EMPTY = DecisionResult(Decision.review, 0.0, (), ReasonCode.no_candidates)


class EmitLinkTest(unittest.TestCase):
    def test_emit_linked_builds_link_proposal(self):
        env = emit(_section(), _audit(), LINKED, pipeline_run_id=RUN, at=AT)
        self.assertEqual(env.status, "linked")
        self.assertEqual(env.schema_version, SCHEMA_VERSION)
        self.assertEqual(env.chunk_id, "chk:owasp/x@abcdef1:a.md")
        self.assertEqual(env.pipeline_run_id, RUN)
        self.assertEqual(len(env.links), 1)
        self.assertEqual(env.links[0].cre_id, "616-305")
        self.assertEqual(env.links[0].link_type, AUTO_LINK_TYPE)
        self.assertEqual(env.links[0].confidence, 0.91)
        self.assertEqual(env.knowledge.text, _section().text)
        self.assertEqual(env.retrieval.threshold, 0.8)  # audit passed through

    def test_degraded_update_detection_default(self):
        env = emit(_section(), _audit(), LINKED, pipeline_run_id=RUN, at=AT)
        self.assertFalse(
            env.update_detection.is_update
        )  # declared-degraded until SafetyGuard

    def test_build_link_proposal_rejects_review(self):
        with self.assertRaises(EmitterError):
            build_link_proposal(
                _section(), _audit(), REVIEW_LOW, pipeline_run_id=RUN, at=AT
            )

    def test_link_needs_a_cre(self):
        bad = DecisionResult(Decision.linked, 0.9, (), None)
        with self.assertRaises(EmitterError):
            build_link_proposal(_section(), _audit(), bad, pipeline_run_id=RUN, at=AT)


class EmitReviewTest(unittest.TestCase):
    def test_emit_review_builds_review_item(self):
        env = emit(_section(), _audit(), REVIEW_LOW, pipeline_run_id=RUN, at=AT)
        self.assertEqual(env.status, "review_required")
        self.assertEqual(env.reason_code, ReasonCode.below_threshold)
        self.assertEqual(
            env.review_id, "review:chk:owasp/x@abcdef1:a.md"
        )  # deterministic
        self.assertIsNotNone(env.suggested_links)
        self.assertEqual(env.suggested_links[0].cre_id, "616-305")
        # a review suggestion is a candidate, not an auto-link — must not claim it
        self.assertEqual(env.suggested_links[0].link_type, SUGGESTED_LINK_TYPE)
        self.assertNotEqual(env.suggested_links[0].link_type, AUTO_LINK_TYPE)

    def test_no_candidates_review_has_no_suggestions(self):
        env = emit(_section(), _audit(), REVIEW_EMPTY, pipeline_run_id=RUN, at=AT)
        self.assertEqual(env.reason_code, ReasonCode.no_candidates)
        self.assertIsNone(env.suggested_links)

    def test_build_review_item_rejects_linked(self):
        with self.assertRaises(EmitterError):
            build_review_item(_section(), _audit(), LINKED, pipeline_run_id=RUN, at=AT)

    def test_review_needs_reason_code(self):
        bad = DecisionResult(Decision.review, 0.4, ("616-305",), None)
        with self.assertRaises(EmitterError):
            build_review_item(_section(), _audit(), bad, pipeline_run_id=RUN, at=AT)


class MetadataTest(unittest.TestCase):
    def test_link_types_match_cre_defs(self):
        from application.defs.cre_defs import LinkTypes

        self.assertEqual(AUTO_LINK_TYPE, LinkTypes.AutomaticallyLinkedTo.value)
        self.assertEqual(SUGGESTED_LINK_TYPE, LinkTypes.Related.value)


if __name__ == "__main__":
    unittest.main()
