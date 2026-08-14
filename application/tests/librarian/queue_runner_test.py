"""End-to-end tests for the live B->C path (``run_librarian_queue``).

Real Module B rows in an in-memory SQLite DB, real C.0->C.4 code, stub C.1/C.2/C.3
— so the wiring under test is exactly the wiring that runs in production, minus
the embedding API and the cross-encoder.

The claims worth proving here are the ones that only appear once both ends are
connected: a queue row becomes an envelope, a finished row gets retired, an
errored row does not, and a second run is a no-op rather than a re-run.
"""

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow
from application.utils.librarian.config_loader import LibrarianConfig
from application.utils.librarian.envelope_sink import NullEnvelopeSink
from application.utils.librarian.factory import LibrarianComponents
from application.utils.librarian.queue_runner import RunSummary, run_librarian_queue
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

AT = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
RUN = "run-1"


def _config(threshold: float = 0.80) -> LibrarianConfig:
    return LibrarianConfig(
        crossencoder_model="stub",
        retriever_backend="in_memory",
        top_k_retrieval=20,
        top_k_rerank=5,
        link_threshold=threshold,
        temperature=1.0,
        batch_size=32,
        ece_target=0.10,
        conformal_alpha=0.10,
    )


def _row(row_id: str, **overrides) -> KnowledgeQueueRow:
    values = dict(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:art:OWASP/ASVS:a.md:{row_id}",
        artifact_id="art:OWASP/ASVS:a.md",
        pipeline_run_id=RUN,
        schema_version="0.2.0",
        source_type="github",
        source_repo="OWASP/ASVS",
        source_commit_sha="abc1234567890",
        source_committed_at="2026-05-24T18:02:11Z",
        locator_kind="repo_path",
        locator_path="a.md",
        span_index=0,
        span_total=1,
        text="Verify that passwords are at least 12 characters.",
        llm_label="KNOWLEDGE",
        confidence=0.9,
        created_at=datetime(2026, 5, 25, 2, 25, 0, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return KnowledgeQueueRow(**values)


class _Retriever:
    def retrieve(self, text: str) -> RetrievalAudit:
        return RetrievalAudit(
            retriever="stub/1.0.0",
            candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
            reranked=[],
            threshold=0.0,
        )


class _Reranker:
    def __init__(self, logit: float = 20.0) -> None:
        self._logit = logit

    def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
        return audit.model_copy(
            update={
                "reranked": [
                    CreCandidate(cre_id="616-305", score_rerank=self._logit),
                    CreCandidate(cre_id="999-999", score_rerank=0.0),
                ]
            }
        )


class _Scaler:
    """Returns a fixed confidence, so the auto-link branch is chosen by the test."""

    def __init__(self, confidence: float) -> None:
        self._confidence = confidence

    def confidence(self, logits) -> float:
        return self._confidence


class _ExplodingRetriever:
    def retrieve(self, text: str) -> RetrievalAudit:
        raise RuntimeError("embedding API timed out")


class _RecordingSink:
    """A persisting sink that keeps the batch in memory for assertions."""

    def __init__(self) -> None:
        self.envelopes: list = []

    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes) -> int:
        self.envelopes.extend(envelopes)
        return len(envelopes)


class _ExplodingSink:
    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes) -> int:
        raise IOError("disk full")


def _components(confidence: float = 0.95, retriever=None) -> LibrarianComponents:
    return LibrarianComponents(
        retriever=retriever or _Retriever(),
        reranker=_Reranker(),
        scaler=_Scaler(confidence),
        known_cre_ids=frozenset({"616-305"}),
    )


class RunLibrarianQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _consumed_at(self, row_id: str):
        return sqla.session.get(KnowledgeQueueRow, row_id).consumed_at

    def _run(self, **kwargs):
        kwargs.setdefault("sink", _RecordingSink())
        return run_librarian_queue(
            sqla.session,
            RUN,
            kwargs.pop("components", None) or _components(),
            _config(),
            at=AT,
            **kwargs,
        )

    def test_queue_row_becomes_a_link_and_is_consumed(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        summary = self._run()

        self.assertEqual((summary.read, summary.linked, summary.review), (1, 1, 0))
        self.assertEqual(summary.consumed, 1)
        self.assertIsNotNone(self._consumed_at("a"))

    def test_low_confidence_routes_to_review_and_still_consumes(self) -> None:
        """A review is a completed decision, not a failure — the row is done."""
        sqla.session.add(_row("a"))
        sqla.session.commit()

        summary = self._run(components=_components(confidence=0.10))

        self.assertEqual((summary.linked, summary.review), (0, 1))
        self.assertEqual(summary.consumed, 1)

    def test_envelope_carries_the_rows_own_identity(self) -> None:
        """The point of the W8 schema fix, asserted end to end."""
        sqla.session.add(_row("a"))
        sqla.session.commit()

        run_librarian_queue(
            sqla.session, RUN, _components(), _config(), at=AT, dry_run=True
        )
        # dry_run leaves state alone; re-read through the pipeline to inspect.
        from application.utils.librarian.knowledge_source import DbKnowledgeSource
        from application.utils.librarian.section_validator import (
            section_from_queue_row,
        )

        item = next(iter(DbKnowledgeSource(sqla.session).items()))
        section = section_from_queue_row(item)
        self.assertEqual(section.chunk_id, "chk:art:OWASP/ASVS:a.md:a")
        self.assertEqual(section.artifact_id, "art:OWASP/ASVS:a.md")

    def test_errored_row_is_left_unconsumed_for_retry(self) -> None:
        """A timeout is transient; retiring the row would lose the chunk."""
        sqla.session.add(_row("a"))
        sqla.session.commit()

        summary = self._run(components=_components(retriever=_ExplodingRetriever()))

        self.assertEqual(summary.errored, 1)
        self.assertEqual(summary.consumed, 0)
        self.assertIsNone(self._consumed_at("a"))

    def test_second_run_is_a_no_op(self) -> None:
        """Consumption is what stops the queue being reprocessed forever."""
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()

        first = self._run()
        second = self._run()

        self.assertEqual((first.read, first.consumed), (2, 2))
        self.assertEqual((second.read, second.consumed), (0, 0))

    def test_dry_run_reads_and_decides_but_stamps_nothing(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        summary = self._run(dry_run=True)

        self.assertEqual((summary.read, summary.linked), (1, 1))
        self.assertEqual(summary.consumed, 0)
        self.assertIsNone(self._consumed_at("a"))

    def test_only_the_named_run_is_drained(self) -> None:
        sqla.session.add_all([_row("a"), _row("b", pipeline_run_id="other-run")])
        sqla.session.commit()

        summary = self._run()

        self.assertEqual(summary.read, 1)
        self.assertIsNone(self._consumed_at("b"))

    def test_uncertain_rows_are_never_touched(self) -> None:
        """They are Module D's queue; C must not drain them."""
        sqla.session.add_all([_row("a"), _row("d", llm_label="UNCERTAIN")])
        sqla.session.commit()

        summary = self._run()

        self.assertEqual(summary.read, 1)
        self.assertIsNone(self._consumed_at("d"))

    def test_boundary_rejection_is_consumed_not_retried(self) -> None:
        """A row C can never link is finished with; re-reading it forever is
        worse than retiring it, and the count keeps it visible."""
        sqla.session.add(_row("a", text="   "))
        sqla.session.commit()

        summary = self._run()

        self.assertEqual((summary.skipped, summary.linked), (1, 0))
        self.assertEqual(summary.consumed, 1)

    def test_real_run_without_a_sink_is_refused(self) -> None:
        """The rule that keeps a drain lossless: no consumption without
        somewhere for the envelopes to land."""
        sqla.session.add(_row("a"))
        sqla.session.commit()

        with self.assertRaises(ValueError) as ctx:
            run_librarian_queue(sqla.session, RUN, _components(), _config(), at=AT)

        self.assertIn("EnvelopeSink", str(ctx.exception))
        self.assertIsNone(self._consumed_at("a"))

    def test_real_run_behind_a_non_persisting_sink_is_refused(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        with self.assertRaises(ValueError):
            run_librarian_queue(
                sqla.session,
                RUN,
                _components(),
                _config(),
                at=AT,
                sink=NullEnvelopeSink(),
            )

        self.assertIsNone(self._consumed_at("a"))

    def test_a_failing_sink_consumes_nothing(self) -> None:
        """Persist first, retire second: if the write fails the rows stay B's
        to hand back, and the whole run is retried."""
        sqla.session.add(_row("a"))
        sqla.session.commit()

        with self.assertRaises(IOError):
            self._run(sink=_ExplodingSink())

        self.assertIsNone(self._consumed_at("a"))

    def test_envelopes_reach_the_sink_before_rows_are_retired(self) -> None:
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()
        sink = _RecordingSink()

        summary = self._run(sink=sink)

        self.assertEqual(summary.persisted, 2)
        self.assertEqual(
            sorted(e.chunk_id for e in sink.envelopes),
            ["chk:art:OWASP/ASVS:a.md:a", "chk:art:OWASP/ASVS:a.md:b"],
        )

    def test_unevaluated_safety_path_is_reported_not_hidden(self) -> None:
        """No SafetyGuard exists yet, so every row is decided without it. That
        has to show up in the summary rather than look like a clean result."""
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()

        with self.assertLogs(
            "application.utils.librarian.queue_runner", level="WARNING"
        ) as logs:
            summary = self._run()

        self.assertEqual(summary.safety_unevaluated, 2)
        self.assertIn("safety path", "\n".join(logs.output))

    def test_summary_serializes_for_the_orchestrator(self) -> None:
        import json

        sqla.session.add(_row("a"))
        sqla.session.commit()

        payload = json.loads(self._run().to_json())

        self.assertEqual(payload["run_id"], RUN)
        self.assertEqual(payload["linked"], 1)

    def test_status_declares_a_degraded_run(self) -> None:
        """The orchestrator branches on ``status``; a constant "ok" would hide
        exactly the runs worth noticing.

        Every row today is decided behind ``NullSafetyGuard``, so a real run is
        genuinely degraded until a detector exists — and the field says which
        rows and why, rather than leaving the reader to know that a non-zero
        ``safety_unevaluated`` is bad news.
        """
        sqla.session.add(_row("a"))
        sqla.session.commit()

        summary = self._run()

        self.assertTrue(summary.safety_unevaluated)
        self.assertIn("degraded", summary.status)
        self.assertIn("safety path", summary.status)

    def test_blank_run_id_is_refused(self) -> None:
        """A blank id is a caller mistake, not "every run".

        `DbKnowledgeSource` applies the scope filter behind a truthiness test, so
        a blank string would drain and consume every run's rows and stamp the
        blank id onto every envelope — unrecoverable once the rows are retired.
        """
        sqla.session.add(_row("a"))
        sqla.session.commit()

        for blank in ("", "   "):
            with self.assertRaises(ValueError):
                run_librarian_queue(
                    sqla.session,
                    blank,
                    _components(),
                    _config(),
                    at=AT,
                    sink=_RecordingSink(),
                )

        # Nothing was read and nothing was retired.
        self.assertIsNone(self._consumed_at("a"))

    def test_unmodellable_row_is_retired_not_re_read_forever(self) -> None:
        """A row B wrote that C cannot model never reaches the pipeline, so the
        pipeline cannot report it finished. Without retiring it here the next run
        reads the same poison row again, and every run after that."""
        good = _row("a")
        # locator_kind is a required enum; an unknown value fails C's model.
        bad = _row("b", locator_kind="not_a_locator_kind")
        sqla.session.add_all([good, bad])
        sqla.session.commit()

        summary = self._run()

        self.assertEqual(summary.linked, 1)
        self.assertIsNotNone(self._consumed_at("a"))
        # The unmodellable row is finished with, and counted rather than hidden.
        self.assertIsNotNone(self._consumed_at("b"))
        self.assertGreaterEqual(summary.skipped, 1)

        # A second run therefore has nothing left to do.
        self.assertEqual(self._run().read, 0)

    def test_status_is_ok_when_there_is_nothing_to_declare(self) -> None:
        summary = RunSummary(run_id=RUN, read=3, linked=3)
        summary.finalize_status()
        self.assertEqual(summary.status, "ok")

    def test_status_names_errored_rows(self) -> None:
        summary = RunSummary(run_id=RUN, read=3, linked=2, errored=1)
        summary.finalize_status()
        self.assertIn("1 errored", summary.status)


if __name__ == "__main__":
    unittest.main()
