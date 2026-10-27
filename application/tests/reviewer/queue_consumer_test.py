"""Tests for D's write-back: the stamp that retires a review row.

The claim that matters most: a ``linked`` row can NEVER be stamped by this path,
whatever id it is handed. That guard is what makes the human queue structurally
unable to retire the graph writer's rows.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database.db import DecisionQueueItem
from application.utils.librarian.envelope_sink import DbEnvelopeSink
from application.utils.reviewer.queue_consumer import mark_reviewed
from application.tests.reviewer._envelopes import RUN, linked, review

AT = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)


class MarkReviewedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        DbEnvelopeSink(sqla.session, RUN).write([review("chk:1"), linked("chk:9")])
        sqla.session.commit()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _row(self, chunk_id: str) -> DecisionQueueItem:
        return (
            sqla.session.query(DecisionQueueItem)
            .filter(DecisionQueueItem.chunk_id == chunk_id)
            .one()
        )

    def test_stamps_review_rows_idempotently(self) -> None:
        rid = self._row("chk:1").id

        self.assertEqual(mark_reviewed(sqla.session, [rid], at=AT), 1)
        sqla.session.commit()
        # A replay cannot move a timestamp that is already set.
        self.assertEqual(mark_reviewed(sqla.session, [rid], at=AT), 0)
        self.assertIsNotNone(self._row("chk:1").consumed_at)

    def test_a_linked_row_can_never_be_stamped_by_the_review_path(self) -> None:
        """linked rows are the graph writer's. Even handed the right id, the
        human-review write-back must refuse — silently, counted in the gap
        between ids passed and rows stamped."""
        rid = self._row("chk:9").id

        self.assertEqual(mark_reviewed(sqla.session, [rid], at=AT), 0)
        sqla.session.commit()

        self.assertIsNone(self._row("chk:9").consumed_at)

    def test_stamp_is_stored_naive_utc(self) -> None:
        """Aware datetime in, naive UTC stored — the pipeline-wide convention,
        dialect-portable."""
        rid = self._row("chk:1").id
        mark_reviewed(sqla.session, [rid], at=AT)
        sqla.session.commit()

        stored = self._row("chk:1").consumed_at
        self.assertIsNone(stored.tzinfo)
        self.assertEqual(stored, AT.astimezone(timezone.utc).replace(tzinfo=None))

    def test_empty_and_falsy_ids_are_a_no_op(self) -> None:
        self.assertEqual(mark_reviewed(sqla.session, [], at=AT), 0)
        self.assertEqual(mark_reviewed(sqla.session, ["", None], at=AT), 0)


if __name__ == "__main__":
    unittest.main()
