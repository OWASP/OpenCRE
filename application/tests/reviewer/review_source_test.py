"""Tests for Module D's read side over ``decision_queue``.

Rows are seeded through the real ``DbEnvelopeSink``, so what these tests prove
is the actual handoff: the envelope C persisted validates back into the same
RFC model on D's side. The behaviour that matters is what the source refuses to
read — ``linked`` rows (the graph writer's), consumed rows, other runs' rows —
and that a row D cannot model is surfaced, skipped, and never retired.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from datetime import datetime
from unittest.mock import patch

from application import create_app, sqla
from application.database.db import DecisionQueueItem
from application.utils.librarian.envelope_sink import DbEnvelopeSink
from application.utils.reviewer.queue_consumer import mark_reviewed
from application.utils.reviewer.review_source import DbReviewSource
from application.tests.reviewer._envelopes import RUN, linked, review


def _seed(*envelopes, run: str = RUN) -> None:
    sink = DbEnvelopeSink(sqla.session, run)
    sink.write(list(envelopes))
    sqla.session.commit()


class DbReviewSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_reads_only_review_required_rows(self) -> None:
        """linked rows belong to the graph writer; a human inbox that showed
        them would invite retiring an auto-link by hand."""
        _seed(review("chk:1"), linked("chk:9"))

        items = list(DbReviewSource(sqla.session).items())

        self.assertEqual([i.chunk_id for i in items], ["chk:1"])

    def test_envelope_round_trips_through_the_real_sink(self) -> None:
        """What C persisted validates back into the same pinned RFC model."""
        _seed(review("chk:1"))

        (item,) = DbReviewSource(sqla.session).items()

        self.assertEqual(item.envelope.review_id, "review:chk:1")
        self.assertEqual(item.envelope.reason_code.value, "BELOW_THRESHOLD")
        self.assertEqual(item.envelope.suggested_links[0].cre_id, "616-305")
        self.assertEqual(item.reason_code, "BELOW_THRESHOLD")
        self.assertEqual(item.source_label, None)

    def test_consumed_rows_are_not_re_read(self) -> None:
        from datetime import datetime

        _seed(review("chk:1"), review("chk:2"))
        row = (
            sqla.session.query(DecisionQueueItem)
            .filter(DecisionQueueItem.chunk_id == "chk:1")
            .one()
        )
        row.consumed_at = datetime(2026, 9, 17)
        sqla.session.commit()

        items = list(DbReviewSource(sqla.session).items())

        self.assertEqual([i.chunk_id for i in items], ["chk:2"])

    def test_scopes_to_one_pipeline_run(self) -> None:
        _seed(review("chk:1"))
        _seed(review("chk:2", run="run-2"), run="run-2")

        items = list(DbReviewSource(sqla.session, pipeline_run_id="run-2").items())

        self.assertEqual([i.chunk_id for i in items], ["chk:2"])

    def test_limit_is_applied_in_a_stable_order(self) -> None:
        _seed(review("chk:3"), review("chk:1"), review("chk:2"))

        first = [i.row_id for i in DbReviewSource(sqla.session, limit=2).items()]
        again = [i.row_id for i in DbReviewSource(sqla.session, limit=2).items()]

        self.assertEqual(len(first), 2)
        self.assertEqual(first, again)

    def test_unreadable_envelope_is_skipped_reported_and_never_consumed(self) -> None:
        """A decision row D cannot parse is C's audit record of a decision.
        Retiring it would hide a C-side contract breach from the one queue a
        human watches, so it is surfaced instead — the opposite of C's
        poison-row policy, deliberately."""
        _seed(review("chk:1"))
        sqla.session.add(
            DecisionQueueItem(
                chunk_id="chk:bad",
                artifact_id="art:1",
                pipeline_run_id=RUN,
                schema_version="0.2.0",
                status="review_required",
                envelope={"not": "an envelope"},
            )
        )
        sqla.session.commit()

        source = DbReviewSource(sqla.session)
        with self.assertLogs(
            "application.utils.reviewer.review_source", level="WARNING"
        ):
            items = list(source.items())

        self.assertEqual([i.chunk_id for i in items], ["chk:1"])
        self.assertEqual(len(source.unreadable_row_ids), 1)
        bad = sqla.session.get(DecisionQueueItem, source.unreadable_row_ids[0])
        self.assertIsNone(bad.consumed_at)

    def _spoil_first(self, *chunk_ids: str) -> None:
        """Make rows unreadable and oldest, so they head every page."""
        for chunk_id in chunk_ids:
            row = sqla.session.query(DecisionQueueItem).filter_by(chunk_id=chunk_id)
            row.update({"envelope": {"bad": True}, "created_at": datetime(2000, 1, 1)})
        sqla.session.commit()

    def test_unreadable_rows_cannot_starve_a_limited_page(self) -> None:
        _seed(*[review(f"chk:{i}") for i in range(5)])
        self._spoil_first("chk:0", "chk:1")

        source = DbReviewSource(sqla.session, limit=2)
        items = list(source.items())

        self.assertEqual(2, len(items))
        self.assertEqual(2, len(source.unreadable_row_ids))

    def test_walks_past_a_batch_boundary(self) -> None:
        _seed(*[review(f"chk:{i}") for i in range(7)])
        with patch("application.utils.reviewer.review_source._BATCH_SIZE", 3):
            items = list(DbReviewSource(sqla.session).items())
        self.assertEqual(7, len({i.row_id for i in items}))

    def test_a_row_stamped_during_the_walk_is_not_yielded(self) -> None:
        _seed(*[review(f"chk:{i}") for i in range(4)])
        with patch("application.utils.reviewer.review_source._BATCH_SIZE", 2):
            source = DbReviewSource(sqla.session).items()
            first = next(source)
            pending = sqla.session.query(DecisionQueueItem).filter(
                DecisionQueueItem.id != first.row_id
            )
            last_id = sorted(r.id for r in pending)[-1]
            mark_reviewed(sqla.session, [last_id], at=datetime(2026, 1, 1))
            rest = [i.row_id for i in source]
        self.assertEqual(2, len(rest))
        self.assertNotIn(last_id, rest)

    def test_reading_twice_does_not_double_count_unreadable_rows(self) -> None:
        _seed(review("chk:0"), review("chk:1"))
        self._spoil_first("chk:0")
        source = DbReviewSource(sqla.session)
        list(source.items())
        list(source.items())
        self.assertEqual(1, len(source.unreadable_row_ids))


if __name__ == "__main__":
    unittest.main()
