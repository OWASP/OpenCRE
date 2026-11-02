"""Module C persists decisions in committed batches, so a crash keeps earlier work.

Before: ``run_librarian_queue`` drained the whole run, wrote the envelopes once and
committed once. A crash anywhere lost every decision of the run (a 654-chunk run
takes about two hours). Now each batch of ``commit_every`` rows writes its
decisions and stamps ``consumed_at`` in ONE transaction, then commits.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import dataclasses
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from application import create_app, sqla
from application.database.db import DecisionQueueItem
from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow
from application.tests.librarian.queue_runner_test import (
    AT,
    RUN,
    _ExplodingRetriever,
    _RecordingSink,
    _components,
    _config,
    _row,
)
from application.utils.librarian import queue_runner
from application.utils.librarian.envelope_sink import DbEnvelopeSink
from application.utils.librarian.queue_runner import run_librarian_queue


def _cfg(commit_every: int):
    return dataclasses.replace(_config(), commit_every=commit_every)


def _created(i: int) -> datetime:
    return datetime(2026, 5, 25, 2, 25, i, tzinfo=timezone.utc)


class _FailsOnNthWrite(_RecordingSink):
    def __init__(self, n: int) -> None:
        super().__init__()
        self.calls = 0
        self._n = n

    def write(self, envelopes) -> int:
        self.calls += 1
        if self.calls == self._n:
            raise IOError("host went away")
        return super().write(envelopes)


class _BatchSizes(_RecordingSink):
    def __init__(self) -> None:
        super().__init__()
        self.sizes: list = []

    def write(self, envelopes) -> int:
        self.sizes.append(len(envelopes))
        return super().write(envelopes)


class ChunkedRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _rows(self, n: int) -> None:
        for i in range(n):
            sqla.session.add(_row(f"r{i}", created_at=_created(i)))
        sqla.session.commit()

    def _consumed(self) -> int:
        sqla.session.expire_all()
        return (
            sqla.session.query(KnowledgeQueueRow)
            .filter(KnowledgeQueueRow.consumed_at.isnot(None))
            .count()
        )

    def _run(self, commit_every: int, **kwargs):
        kwargs.setdefault("sink", _RecordingSink())
        return run_librarian_queue(
            sqla.session,
            RUN,
            kwargs.pop("components", None) or _components(),
            _cfg(commit_every),
            at=AT,
            **kwargs,
        )

    # ---- commits in batches ------------------------------------------------
    def test_decisions_are_written_and_committed_per_batch(self) -> None:
        self._rows(7)
        sink = _BatchSizes()
        with patch.object(sqla.session, "commit", wraps=sqla.session.commit) as commit:
            summary = self._run(3, sink=sink)
        self.assertEqual(sink.sizes, [3, 3, 1])
        self.assertEqual(commit.call_count, 3)
        self.assertEqual((summary.read, summary.linked, summary.consumed), (7, 7, 7))
        self.assertEqual(summary.persisted, 7)
        self.assertEqual(summary.status, "ok")

    def test_zero_keeps_the_old_single_write(self) -> None:
        self._rows(7)
        sink = _BatchSizes()
        self._run(0, sink=sink)
        self.assertEqual(sink.sizes, [7])

    def test_dry_run_is_one_pass_and_persists_nothing(self) -> None:
        self._rows(5)
        summary = self._run(2, sink=None, dry_run=True)
        self.assertEqual((summary.read, summary.consumed), (5, 0))
        self.assertEqual(self._consumed(), 0)

    # ---- crash and resume --------------------------------------------------
    def test_a_crash_keeps_the_batches_already_committed(self) -> None:
        self._rows(7)
        with self.assertRaises(IOError):
            self._run(3, sink=_FailsOnNthWrite(3))
        sqla.session.rollback()  # what a dead process does to its open transaction
        self.assertEqual(self._consumed(), 6)

    def test_rerun_resumes_with_only_the_remainder_and_no_duplicates(self) -> None:
        self._rows(7)
        with self.assertRaises(IOError):
            self._run(
                3,
                sink=_FailsOnNthWrite(3),
            )
        sqla.session.rollback()
        # Real sink this time: decisions of the first two batches must already be there.
        first = DbEnvelopeSink(sqla.session, RUN)
        summary = self._run(3, sink=first)
        self.assertEqual(summary.read, 1)  # only the remainder
        self.assertEqual(summary.consumed, 1)
        self.assertEqual(self._consumed(), 7)

    def test_crash_and_resume_end_with_every_decision_exactly_once(self) -> None:
        self._rows(7)

        class _DbThenCrash(DbEnvelopeSink):
            calls = 0

            def write(self, envelopes):
                type(self).calls += 1
                written = super().write(envelopes)
                if type(self).calls == 3:
                    raise IOError("died after inserting, before commit")
                return written

        with self.assertRaises(IOError):
            self._run(3, sink=_DbThenCrash(sqla.session, RUN))
        sqla.session.rollback()
        # batch 3's insert and stamp were in the uncommitted transaction: both gone
        self.assertEqual(sqla.session.query(DecisionQueueItem).count(), 6)
        self._run(3, sink=DbEnvelopeSink(sqla.session, RUN))
        chunks = [d.chunk_id for d in sqla.session.query(DecisionQueueItem).all()]
        self.assertEqual(len(chunks), 7)
        self.assertEqual(len(set(chunks)), 7)

    # ---- termination and limits -------------------------------------------
    def test_errored_rows_are_retried_next_run_but_not_reread_within_one(self) -> None:
        self._rows(4)
        summary = self._run(2, components=_components(retriever=_ExplodingRetriever()))
        self.assertEqual((summary.read, summary.errored, summary.consumed), (4, 4, 0))
        self.assertTrue(summary.status.startswith("degraded"))

    def test_limit_still_caps_the_whole_run(self) -> None:
        self._rows(7)
        summary = self._run(2, limit=5)
        self.assertEqual((summary.read, summary.consumed), (5, 5))
        self.assertEqual(self._consumed(), 5)

    # ---- same result as before --------------------------------------------
    def test_envelopes_equal_the_single_write_result(self) -> None:
        self._rows(7)
        single = _RecordingSink()
        self._run(0, sink=single)
        sqla.session.query(KnowledgeQueueRow).update({"consumed_at": None})
        sqla.session.commit()
        chunked = _RecordingSink()
        self._run(3, sink=chunked)
        dump = lambda s: [e.model_dump(mode="json") for e in s.envelopes]
        self.assertEqual(dump(single), dump(chunked))

    def test_family_counts_come_from_the_whole_run_not_each_batch(self) -> None:
        self._rows(7)
        seen = []
        real = queue_runner.LibrarianPipeline

        def _spy(*args, **kwargs):
            seen.append(kwargs.get("resource_family_counts"))
            return real(*args, **kwargs)

        components = dataclasses.replace(_components(), leaf_drilldown=True)
        with patch.object(queue_runner, "LibrarianPipeline", side_effect=_spy):
            self._run(3, components=components)
        self.assertEqual(len(seen), 4)  # 3 + 3 + 1 rows, then the empty probe
        whole = {next(iter(seen[0])): 7}
        for counts in seen:
            self.assertEqual(counts, whole)

    # ---- progress ---------------------------------------------------------
    def test_progress_is_logged_per_batch(self) -> None:
        self._rows(7)
        with self.assertLogs(queue_runner.logger, level="INFO") as logs:
            self._run(3)
        text = "\n".join(logs.output)
        self.assertIn("decided 3 of 7", text)
        self.assertIn("decided 6 of 7", text)
        self.assertIn("decided 7 of 7", text)


if __name__ == "__main__":
    unittest.main()
