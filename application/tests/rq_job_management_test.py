"""Admin OIE RQ requeue / cancel helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from application.utils import rq_dashboard_snapshot as snap


class RequeueFailedOieJobsTest(unittest.TestCase):
    @patch.object(
        snap, "queue_summary", return_value={"oie": {"failed": 0, "queued": 1}}
    )
    @patch.object(snap, "_fetch_job")
    @patch.object(snap, "FailedJobRegistry")
    @patch.object(snap, "Queue")
    @patch.object(snap.redis, "connect")
    def test_requeue_all_oie_prefix(
        self,
        _connect: MagicMock,
        queue_cls: MagicMock,
        reg_cls: MagicMock,
        fetch: MagicMock,
        _summary: MagicMock,
    ) -> None:
        reg = reg_cls.return_value
        reg.get_job_ids.return_value = ["a", "b", "c"]
        job_oie = MagicMock(description="oie:c:art:OWASP/x:README.md")
        job_other = MagicMock(description="ga:pair")
        fetch.side_effect = lambda _conn, _q, jid: {
            "a": job_oie,
            "b": job_other,
            "c": job_oie,
        }[jid]

        out = snap.requeue_failed_oie_jobs()
        self.assertEqual(out["requeued_count"], 2)
        self.assertEqual(sorted(out["requeued"]), ["a", "c"])
        self.assertEqual(reg.requeue.call_count, 2)

    @patch.object(snap, "queue_summary", return_value={})
    @patch.object(snap, "FailedJobRegistry")
    @patch.object(snap, "Queue")
    @patch.object(snap.redis, "connect")
    def test_requeue_explicit_ids(
        self,
        _connect: MagicMock,
        _queue_cls: MagicMock,
        reg_cls: MagicMock,
        _summary: MagicMock,
    ) -> None:
        reg = reg_cls.return_value
        reg.get_job_ids.return_value = ["keep", "gone"]
        out = snap.requeue_failed_oie_jobs(job_ids=["keep", "missing"])
        self.assertEqual(out["requeued"], ["keep"])
        self.assertEqual(out["missing"], ["missing"])
        reg.requeue.assert_called_once_with("keep")


class CancelOieJobsTest(unittest.TestCase):
    @patch.object(snap, "queue_summary", return_value={})
    @patch.object(snap, "_fetch_job")
    @patch.object(snap, "Queue")
    @patch.object(snap.redis, "connect")
    def test_cancel_oie_only(
        self,
        _connect: MagicMock,
        _queue_cls: MagicMock,
        fetch: MagicMock,
        _summary: MagicMock,
    ) -> None:
        oie = MagicMock(description="oie:b:art:x")
        other = MagicMock(description="import:y")
        fetch.side_effect = lambda _c, _q, jid: {"1": oie, "2": other, "3": None}[jid]
        out = snap.cancel_oie_jobs(["1", "2", "3"])
        self.assertEqual(out["cancelled"], ["1"])
        self.assertEqual(out["missing"], ["3"])
        self.assertEqual(len(out["errors"]), 1)
        oie.cancel.assert_called_once()
        other.cancel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
