"""Tests for the C -> D handoff (``DbEnvelopeSink`` -> ``decision_queue``).

Real rows in an in-memory SQLite DB through the real model, because the claims
worth proving here only exist once the table is involved: a decision becomes a
row Module D can filter, a replay does not duplicate it, and the envelope that
lands is the same RFC document ``JsonlEnvelopeSink`` would have written.
"""

import json
import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database.db import DecisionQueueItem
from application.utils.librarian.envelope_sink import (
    DbEnvelopeSink,
    NullEnvelopeSink,
    TeeEnvelopeSink,
)
from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    CreCandidate,
    KnowledgeSnapshot,
    LinkProposal,
    Locator,
    ProposedLink,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
    SourceRef,
    UpdateDetection,
)

AT = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
RUN = "run-1"


def _knowledge() -> KnowledgeSnapshot:
    return KnowledgeSnapshot(
        text="Verify passwords are at least 12 characters.",
        source=SourceRef(
            type="github",
            repo="OWASP/ASVS",
            commit_sha="abc1234567890",
            committed_at=AT,
        ),
        locator=Locator(kind="repo_path", id="a.md", path="a.md"),
    )


def _audit() -> RetrievalAudit:
    return RetrievalAudit(
        retriever="stub/1.0.0",
        candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
        reranked=[CreCandidate(cre_id="616-305", score_rerank=4.0)],
        threshold=0.8,
    )


def _linked(chunk_id: str = "chk:1", confidence: float = 0.95) -> LinkProposal:
    return LinkProposal(
        schema_version=SCHEMA_VERSION,
        chunk_id=chunk_id,
        artifact_id="art:1",
        pipeline_run_id=RUN,
        classified_at=AT,
        knowledge=_knowledge(),
        retrieval=_audit(),
        links=[
            ProposedLink(
                cre_id="616-305",
                link_type="Automatically linked to",
                confidence=confidence,
            )
        ],
        update_detection=UpdateDetection(is_update=False),
    )


def _review(chunk_id: str = "chk:2") -> ReviewItem:
    return ReviewItem(
        schema_version=SCHEMA_VERSION,
        review_id=f"review:{chunk_id}",
        chunk_id=chunk_id,
        artifact_id="art:1",
        pipeline_run_id=RUN,
        created_at=AT,
        reason_code=ReasonCode.below_threshold,
        knowledge=_knowledge(),
        retrieval=_audit(),
        suggested_links=[
            ProposedLink(cre_id="616-305", link_type="Related to", confidence=0.42)
        ],
        update_detection=UpdateDetection(is_update=False),
    )


class DbEnvelopeSinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.sink = DbEnvelopeSink(sqla.session, RUN)

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _rows(self):
        return sqla.session.query(DecisionQueueItem).order_by("chunk_id").all()

    def test_declares_that_it_persists(self) -> None:
        # The runner retires queue rows on the strength of this.
        self.assertTrue(self.sink.persists)

    def test_a_linked_decision_becomes_a_row_module_d_can_filter(self) -> None:
        self.assertEqual(self.sink.write([_linked()]), 1)
        sqla.session.commit()

        (row,) = self._rows()
        self.assertEqual(row.status, "linked")
        self.assertEqual(row.chunk_id, "chk:1")
        self.assertEqual(row.artifact_id, "art:1")
        self.assertEqual(row.pipeline_run_id, RUN)
        self.assertAlmostEqual(row.confidence, 0.95)
        # A link has no reason to review, so the column stays empty.
        self.assertIsNone(row.reason_code)
        self.assertIsNone(row.review_id)
        # D has not seen it yet.
        self.assertIsNone(row.consumed_at)

    def test_a_review_decision_carries_its_reason_code(self) -> None:
        """The whole point of a review row: D needs to know *why* it is here."""
        self.sink.write([_review()])
        sqla.session.commit()

        (row,) = self._rows()
        self.assertEqual(row.status, "review_required")
        self.assertEqual(row.reason_code, "BELOW_THRESHOLD")
        self.assertEqual(row.review_id, "review:chk:2")
        self.assertAlmostEqual(row.confidence, 0.42)

    def test_both_outcomes_share_the_table(self) -> None:
        # Same handoff shape as B's queue: one table, readers filter on status.
        self.sink.write([_linked("chk:1"), _review("chk:2")])
        sqla.session.commit()

        self.assertEqual(
            [r.status for r in self._rows()], ["linked", "review_required"]
        )

    def test_the_whole_rfc_envelope_is_stored(self) -> None:
        """The columns are projections; the envelope is the record of truth."""
        self.sink.write([_linked()])
        sqla.session.commit()

        (row,) = self._rows()
        envelope = row.envelope
        self.assertEqual(envelope["status"], "linked")
        self.assertEqual(envelope["chunk_id"], "chk:1")
        # The retrieval audit travels with it, so a decision stays explainable.
        self.assertIn("retrieval", envelope)
        self.assertEqual(envelope["retrieval"]["retriever"], "stub/1.0.0")

    def test_stored_envelope_has_no_nulls(self) -> None:
        # Same rule as the JSONL sink: absent optional fields must be absent
        # keys, or Module D's RFC validator rejects the document.
        self.sink.write([_linked()])
        sqla.session.commit()

        (row,) = self._rows()

        def _nulls(node):
            if isinstance(node, dict):
                for value in node.values():
                    yield from _nulls(value)
            elif isinstance(node, list):
                for value in node:
                    yield from _nulls(value)
            elif node is None:
                yield node

        self.assertEqual(list(_nulls(row.envelope)), [])

    def test_replaying_a_run_does_not_duplicate(self) -> None:
        """A retried run must be a no-op, not a second decision for the chunk."""
        self.assertEqual(self.sink.write([_linked()]), 1)
        sqla.session.commit()

        self.assertEqual(self.sink.write([_linked()]), 0)
        sqla.session.commit()

        self.assertEqual(len(self._rows()), 1)

    def test_a_replay_still_counts_as_persisted(self) -> None:
        """The row is there either way, so the runner may retire behind it.

        Returning 0 for "already written" must not read as "nothing survived" —
        that is the condition the consumption rule turns on.
        """
        self.sink.write([_linked("chk:1")])
        sqla.session.commit()

        # A batch mixing a replayed chunk with a new one writes only the new one.
        self.assertEqual(self.sink.write([_linked("chk:1"), _linked("chk:9")]), 1)
        sqla.session.commit()

        self.assertEqual({r.chunk_id for r in self._rows()}, {"chk:1", "chk:9"})

    def test_the_same_chunk_in_a_later_run_is_a_new_decision(self) -> None:
        """Uniqueness is per (chunk, run) — B may legitimately re-offer a chunk
        in a later pipeline run, and that decision is its own record."""
        self.sink.write([_linked("chk:1")])
        sqla.session.commit()

        later = _linked("chk:1").model_copy(update={"pipeline_run_id": "run-2"})
        DbEnvelopeSink(sqla.session, "run-2").write([later])
        sqla.session.commit()

        self.assertEqual(len(self._rows()), 2)

    def test_empty_batch_writes_nothing(self) -> None:
        self.assertEqual(self.sink.write([]), 0)
        self.assertEqual(self._rows(), [])


class TeeEnvelopeSinkTest(unittest.TestCase):
    def test_reports_the_first_sinks_count(self) -> None:
        primary, mirror = _CountingSink(), _CountingSink()
        tee = TeeEnvelopeSink(primary, mirror)

        self.assertEqual(tee.write([_linked(), _review()]), 2)
        self.assertEqual((primary.written, mirror.written), (2, 2))

    def test_does_not_persist_if_any_sink_discards(self) -> None:
        """Otherwise a run could retire rows on the strength of a copy that
        kept nothing."""
        self.assertFalse(TeeEnvelopeSink(_CountingSink(), NullEnvelopeSink()).persists)

    def test_persists_when_every_sink_does(self) -> None:
        self.assertTrue(TeeEnvelopeSink(_CountingSink(), _CountingSink()).persists)

    def test_needs_at_least_one_sink(self) -> None:
        with self.assertRaises(ValueError):
            TeeEnvelopeSink()


class _CountingSink:
    def __init__(self) -> None:
        self.written = 0

    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes) -> int:
        self.written += len(envelopes)
        return len(envelopes)


if __name__ == "__main__":
    unittest.main()
