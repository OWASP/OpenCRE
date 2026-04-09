import unittest
from unittest.mock import Mock, patch

from application.utils import redis as redis_utils


class TestRedisWaitForJobs(unittest.TestCase):
    @patch("application.utils.redis.time.sleep")
    def test_wait_for_jobs_logs_queue_then_finish_without_hint(self, sleep_mock) -> None:
        job = Mock()
        job.id = "j1"
        job.description = "ASVS->CWE"
        job.kwargs = {}
        statuses = ["queued", "finished"]

        def _status():
            return statuses[0]

        def _is_queued():
            return statuses[0] == "queued"

        def _is_finished():
            return statuses[0] == "finished"

        job.get_status.side_effect = _status
        type(job).is_queued = property(lambda _self: _is_queued())
        type(job).is_finished = property(lambda _self: _is_finished())
        type(job).is_failed = property(lambda _self: False)
        type(job).is_canceled = property(lambda _self: False)
        type(job).is_stopped = property(lambda _self: False)
        type(job).is_started = property(lambda _self: False)

        calls = {"n": 0}

        def _cb():
            calls["n"] += 1

        with patch.object(redis_utils.logger, "info") as info_log, patch.object(
            redis_utils.logger, "warning"
        ) as warn_log:
            def _advance(_seconds):
                statuses[0] = "finished"

            sleep_mock.side_effect = _advance
            redis_utils.wait_for_jobs([job], callback=_cb)

        self.assertEqual(calls["n"], 1)
        warn_log.assert_not_called()
        self.assertTrue(any("queued" in str(c.args[0]) for c in info_log.call_args_list))

    @patch("application.utils.redis.time.sleep")
    @patch.dict("os.environ", {"CRE_REDIS_QUEUE_HINT_AFTER_SECONDS": "0"})
    def test_wait_for_jobs_aggregates_overdue_queue_warnings(self, sleep_mock) -> None:
        jobs = []
        for idx in range(3):
            job = Mock()
            job.id = f"j{idx}"
            job.description = f"A{idx}->B{idx}"
            job.kwargs = {}
            status = {"value": "queued"}

            job.get_status.side_effect = lambda s=status: s["value"]
            type(job).is_queued = property(lambda _self, s=status: s["value"] == "queued")
            type(job).is_finished = property(lambda _self, s=status: s["value"] == "finished")
            type(job).is_failed = property(lambda _self: False)
            type(job).is_canceled = property(lambda _self: False)
            type(job).is_stopped = property(lambda _self: False)
            type(job).is_started = property(lambda _self: False)
            jobs.append((job, status))

        ticks = {"n": 0}

        def _advance(_seconds):
            ticks["n"] += 1
            if ticks["n"] >= 2:
                for _job, st in jobs:
                    st["value"] = "finished"

        sleep_mock.side_effect = _advance
        with patch.object(redis_utils.logger, "warning") as warn_log:
            redis_utils.wait_for_jobs([j for j, _ in jobs], callback=lambda: None)

        self.assertEqual(warn_log.call_count, 1)
        self.assertIn("jobs still queued", warn_log.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
