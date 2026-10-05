import unittest
from datetime import datetime, timedelta, timezone

from application import create_app, sqla
from application.database.db import OieRun
from application.utils.oie_scheduler import lease, run_log

NOW = datetime(2026, 10, 5, 10, 7, 30, tzinfo=timezone.utc)


class SlotTest(unittest.TestCase):
    def test_slot_floors_to_interval(self) -> None:
        self.assertEqual(run_log.slot_for(10, NOW), "20261005T1000Z")
        self.assertEqual(
            run_log.slot_for(10, NOW + timedelta(minutes=3)), "20261005T1010Z"
        )
        self.assertEqual(run_log.slot_for(1440, NOW), "20261005T0000Z")

    def test_naive_input_is_treated_as_utc(self) -> None:
        self.assertEqual(
            run_log.slot_for(10, NOW.replace(tzinfo=None)), "20261005T1000Z"
        )

    def test_run_id_is_slot_derived(self) -> None:
        self.assertEqual(
            run_log.run_id_for("owasp", "20261005T1000Z"), "owasp-20261005T1000Z"
        )

    def test_expected_next_is_start_of_following_slot(self) -> None:
        self.assertEqual(
            run_log.expected_next(10, NOW),
            datetime(2026, 10, 5, 10, 10, tzinfo=timezone.utc),
        )

    def test_non_positive_interval_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_log.slot_for(0, NOW)


class RunLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.session = sqla.session

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _begin(self, slot="20261005T1000Z", **kw):
        return run_log.begin_run(
            self.session,
            "owasp",
            slot,
            trigger="scheduled",
            dry_run=False,
            now=NOW,
            **kw,
        )

    def test_begin_creates_running_row_with_slot_id(self) -> None:
        row = self._begin()
        self.assertEqual(row.id, "owasp-20261005T1000Z")
        self.assertEqual(row.status, "running")
        self.assertEqual(row.attempts, 1)

    def test_finished_slot_is_not_rerun(self) -> None:
        row = self._begin()
        run_log.finish_run(
            self.session, row, status="ok", summary={"a": 1}, error=None, now=NOW
        )
        self.assertIsNone(self._begin())
        self.assertEqual(self.session.query(OieRun).count(), 1)

    def test_degraded_slot_counts_as_done(self) -> None:
        row = self._begin()
        run_log.finish_run(
            self.session, row, status="degraded", summary={}, error=None, now=NOW
        )
        self.assertIsNone(self._begin())

    def test_failed_slot_is_retried_on_the_same_row(self) -> None:
        row = self._begin()
        run_log.finish_run(
            self.session, row, status="error", summary=None, error="boom", now=NOW
        )
        retry = self._begin()
        self.assertEqual(retry.id, row.id)
        self.assertEqual(retry.attempts, 2)
        self.assertEqual(retry.status, "running")
        self.assertIsNone(retry.error)
        self.assertEqual(self.session.query(OieRun).count(), 1)

    def test_force_reruns_a_finished_slot(self) -> None:
        row = self._begin()
        run_log.finish_run(
            self.session, row, status="ok", summary={}, error=None, now=NOW
        )
        again = self._begin(force=True)
        self.assertIsNotNone(again)
        self.assertEqual(again.attempts, 2)

    def test_stale_running_row_from_earlier_slot_is_abandoned(self) -> None:
        self._begin(slot="20261005T0950Z")
        self._begin(slot="20261005T1000Z")
        old = run_log.get_run(self.session, "owasp-20261005T0950Z")
        self.assertEqual(old.status, "abandoned")
        self.assertIsNotNone(old.finished_at)

    def test_list_runs_filters_and_orders_newest_first(self) -> None:
        a = self._begin(slot="20261005T0950Z")
        run_log.finish_run(
            self.session, a, status="ok", summary={}, error=None, now=NOW
        )
        b = run_log.begin_run(
            self.session,
            "cre_expansion",
            "20261005T0000Z",
            trigger="manual",
            dry_run=True,
            now=NOW + timedelta(minutes=1),
        )
        run_log.finish_run(
            self.session, b, status="error", summary=None, error="x", now=NOW
        )
        rows = run_log.list_runs(self.session)
        self.assertEqual([r.job for r in rows], ["cre_expansion", "owasp"])
        self.assertEqual(
            [r.id for r in run_log.list_runs(self.session, job="owasp")], [a.id]
        )
        self.assertEqual(
            [r.id for r in run_log.list_runs(self.session, status="error")], [b.id]
        )

    def test_run_to_dict_reports_duration(self) -> None:
        row = self._begin()
        run_log.finish_run(
            self.session,
            row,
            status="ok",
            summary={"k": 1},
            error=None,
            now=NOW + timedelta(seconds=90),
        )
        data = run_log.run_to_dict(row)
        self.assertEqual(data["duration_seconds"], 90.0)
        self.assertEqual(data["summary"], {"k": 1})
        self.assertEqual(data["id"], "owasp-20261005T1000Z")


class LeaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_second_holder_is_refused_until_release(self) -> None:
        with lease.job_lease(sqla.session, "owasp") as first:
            self.assertTrue(first)
            with lease.job_lease(sqla.session, "owasp") as second:
                self.assertFalse(second)
            with lease.job_lease(sqla.session, "cre_expansion") as other_job:
                self.assertTrue(other_job)
        with lease.job_lease(sqla.session, "owasp") as again:
            self.assertTrue(again)

    def test_lease_key_is_stable_and_distinct_per_job(self) -> None:
        self.assertEqual(lease.lease_key("owasp"), lease.lease_key("owasp"))
        self.assertNotEqual(lease.lease_key("owasp"), lease.lease_key("cre_expansion"))
        self.assertLess(lease.lease_key("owasp"), 2**63)


if __name__ == "__main__":
    unittest.main()
