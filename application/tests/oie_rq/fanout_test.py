"""Unit tests for OIE RQ fan-out helpers (mocked Redis/RQ)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from application.utils.oie_rq.fanout import (
    EnqueueResult,
    _inflight_key,
    enqueue_b_jobs_for_artifacts,
    enqueue_c_job,
    oie_job_timeout,
    oie_queue_name,
    wait_for_oie_queue_idle,
)


class FanoutHelpersTests(unittest.TestCase):
    def test_queue_name_default_and_env(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            # Ensure default when unset or empty after strip handled in helper.
            with patch.dict("os.environ", {"CRE_OIE_QUEUE_NAME": ""}, clear=False):
                self.assertEqual(oie_queue_name(), "oie")
            with patch.dict("os.environ", {"CRE_OIE_QUEUE_NAME": "oie-custom"}):
                self.assertEqual(oie_queue_name(), "oie-custom")

    def test_timeout_falls_back_to_ga_constant(self) -> None:
        with patch.dict("os.environ", {"CRE_OIE_JOB_TIMEOUT": ""}, clear=False):
            self.assertTrue(
                oie_job_timeout().endswith("s") or oie_job_timeout().isdigit()
            )

    def test_inflight_key_shape(self) -> None:
        self.assertEqual(
            _inflight_key("a", "run1", "repo-x"),
            "oie:inflight:a:run1:repo-x",
        )

    @patch("application.utils.oie_rq.fanout.Job.fetch")
    @patch("application.utils.oie_rq.fanout.redis.connect")
    @patch("application.utils.oie_rq.fanout.Queue")
    def test_enqueue_b_skips_when_inflight(
        self, queue_cls: MagicMock, connect: MagicMock, fetch: MagicMock
    ) -> None:
        from rq.job import JobStatus

        conn = MagicMock()
        connect.return_value = conn
        conn.get.return_value = b"existing-job"
        job = MagicMock()
        job.get_status.return_value = JobStatus.QUEUED
        fetch.return_value = job
        ids = enqueue_b_jobs_for_artifacts(
            pipeline_run_id="run1",
            artifact_ids=["art:doc.md"],
            db_connection_str="sqlite:///",
        )
        self.assertEqual(ids, ["existing-job"])
        queue_cls.return_value.enqueue_call.assert_not_called()

    @patch("application.utils.oie_rq.fanout.redis.connect")
    @patch("application.utils.oie_rq.fanout.Queue")
    def test_enqueue_c_records_inflight(
        self, queue_cls: MagicMock, connect: MagicMock
    ) -> None:
        conn = MagicMock()
        connect.return_value = conn
        conn.get.return_value = None
        q = queue_cls.return_value
        job = MagicMock()
        job.id = "jid-c"
        q.enqueue_call.return_value = job
        out = enqueue_c_job(
            pipeline_run_id="run1",
            artifact_id="art:doc.md",
            db_connection_str="sqlite:///",
        )
        self.assertEqual(out, "jid-c")
        conn.set.assert_called()
        q.enqueue_call.assert_called_once()
        kwargs = q.enqueue_call.call_args.kwargs
        self.assertEqual(kwargs["description"], "oie:c:art:doc.md")

    def test_enqueue_result_to_dict(self) -> None:
        r = EnqueueResult(run_id="r", a_job_ids=["1"], repo_ids=["a"])
        d = r.to_dict()
        self.assertEqual(d["run_id"], "r")
        self.assertEqual(d["a_job_ids"], ["1"])

    @patch("time.sleep", return_value=None)
    @patch("application.utils.oie_rq.fanout.oie_queue_inflight_counts")
    @patch("application.utils.oie_rq.fanout.redis.connect")
    def test_wait_idle_requires_stable_polls(
        self,
        connect: MagicMock,
        counts_fn: MagicMock,
        _sleep: MagicMock,
    ) -> None:
        connect.return_value = MagicMock()
        empty = {"queued": 0, "started": 0, "deferred": 0, "scheduled": 0}
        busy = {"queued": 1, "started": 0, "deferred": 0, "scheduled": 0}
        # Gap then three empties → return only after streak of 3.
        counts_fn.side_effect = [busy, empty, empty, empty]
        out = wait_for_oie_queue_idle(poll_seconds=0.01, stable_polls=3)
        self.assertEqual(out, empty)
        self.assertEqual(counts_fn.call_count, 4)


if __name__ == "__main__":
    unittest.main()
