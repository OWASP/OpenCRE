"""Tests for C's write-back to Module B's queue (``mark_consumed``).

In-memory SQLite via ``create_app(mode="test")``, matching ``db_test.py``.

This is the only column Module C writes on B's table, so the tests are about
restraint: stamp exactly the rows asked for, never re-stamp one that is already
consumed, and never delete anything.
"""

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow
from application.utils.librarian.queue_consumer import mark_consumed

AT = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)

# B declared `consumed_at` as a plain `DateTime`, so the driver stores the UTC
# wall clock and hands back a naive value. Compare against that rather than
# against the aware input we wrote.
AT_NAIVE = AT.replace(tzinfo=None)
EARLIER_NAIVE = EARLIER.replace(tzinfo=None)


def _row(row_id: str, **overrides) -> KnowledgeQueueRow:
    values = dict(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:{row_id}",
        artifact_id="art:x",
        pipeline_run_id="run-1",
        schema_version="0.2.0",
        source_type="github",
        source_repo="OWASP/ASVS",
        source_commit_sha="abc1234567890",
        locator_kind="repo_path",
        locator_path="a.md",
        span_index=0,
        span_total=1,
        text="some security text",
        llm_label="KNOWLEDGE",
        confidence=0.9,
        created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return KnowledgeQueueRow(**values)


class MarkConsumedTest(unittest.TestCase):
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

    def test_stamps_only_the_given_rows(self) -> None:
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()

        stamped = mark_consumed(sqla.session, ["a"], at=AT)

        self.assertEqual(stamped, 1)
        self.assertEqual(self._consumed_at("a"), AT_NAIVE)
        self.assertIsNone(self._consumed_at("b"))

    def test_replay_does_not_move_an_existing_timestamp(self) -> None:
        """Idempotence is the point: a re-run must not rewrite when a row was
        first consumed, or the audit trail stops meaning anything."""
        sqla.session.add(_row("a", consumed_at=EARLIER))
        sqla.session.commit()

        stamped = mark_consumed(sqla.session, ["a"], at=AT)

        self.assertEqual(stamped, 0)
        self.assertEqual(self._consumed_at("a"), EARLIER_NAIVE)

    def test_partial_stamp_is_reported_not_raised(self) -> None:
        sqla.session.add_all([_row("a"), _row("b", consumed_at=EARLIER)])
        sqla.session.commit()

        with self.assertLogs(
            "application.utils.librarian.queue_consumer", level="INFO"
        ):
            stamped = mark_consumed(sqla.session, ["a", "b"], at=AT)

        self.assertEqual(stamped, 1)

    def test_unknown_id_is_not_an_error(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        with self.assertLogs(
            "application.utils.librarian.queue_consumer", level="INFO"
        ):
            stamped = mark_consumed(sqla.session, ["a", "ghost"], at=AT)

        self.assertEqual(stamped, 1)

    def test_duplicate_ids_are_counted_once(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        self.assertEqual(mark_consumed(sqla.session, ["a", "a"], at=AT), 1)

    def test_empty_input_touches_nothing(self) -> None:
        sqla.session.add(_row("a"))
        sqla.session.commit()

        self.assertEqual(mark_consumed(sqla.session, [], at=AT), 0)
        self.assertIsNone(self._consumed_at("a"))

    def test_rows_are_never_deleted(self) -> None:
        """The queue is also the audit trail of the B->C handover."""
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()

        mark_consumed(sqla.session, ["a", "b"], at=AT)

        self.assertEqual(sqla.session.query(KnowledgeQueueRow).count(), 2)

    def test_stamps_more_rows_than_one_chunk(self) -> None:
        """The id list is stamped in chunks; the boundary must not drop rows."""
        ids = [f"r{i:04d}" for i in range(1200)]
        sqla.session.add_all([_row(i) for i in ids])
        sqla.session.commit()

        self.assertEqual(mark_consumed(sqla.session, ids, at=AT), 1200)


if __name__ == "__main__":
    unittest.main()
