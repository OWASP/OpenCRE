import unittest
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, patch

from application.utils import gap_analysis


def _response(status: int = 200, body: Any = None) -> MagicMock:
    res = MagicMock()
    res.status_code = status
    res.json.return_value = body if body is not None else {}
    return res


class PreloadTest(unittest.TestCase):
    """preload() polls map_analysis until every pair is cached or given up on."""

    def _run(
        self, standards: List[str], answer: Callable[[str, int], MagicMock]
    ) -> Dict[str, Any]:
        polls: Dict[str, int] = {}

        def fake_get(url: str) -> MagicMock:
            if url.endswith("/rest/v1/standards"):
                return _response(body=standards)
            pair = url.split("standard=", 1)[1].replace("&standard=", "->")
            polls[pair] = polls.get(pair, 0) + 1
            return answer(pair, polls[pair])

        with patch.object(gap_analysis.requests, "get", side_effect=fake_get), patch(
            "application.utils.gap_analysis.time.sleep"
        ) as sleep:
            dropped = gap_analysis.preload(target_url="http://x")
        return {"dropped": dropped, "polls": polls, "sleeps": sleep.call_count}

    def test_all_pairs_cached_needs_one_pass_and_no_sleep(self) -> None:
        out = self._run(["A", "B"], lambda _p, _n: _response(body={"result": {"k": 1}}))
        self.assertEqual([], out["dropped"])
        self.assertEqual({"A->B": 1, "B->A": 1}, out["polls"])
        self.assertEqual(0, out["sleeps"])

    def test_finished_pair_is_not_polled_again(self) -> None:
        def answer(pair: str, n: int) -> MagicMock:
            if pair == "A->B" or n >= 3:
                return _response(body={"result": {"k": 1}})
            return _response(body={"job_id": "job-1"})

        out = self._run(["A", "B"], answer)
        self.assertEqual(1, out["polls"]["A->B"])
        self.assertEqual(3, out["polls"]["B->A"])

    def test_long_running_job_is_not_dropped(self) -> None:
        # GA jobs may run for 36 hours, so polling the same job id is not a failure.
        polls_while_running = gap_analysis.PRELOAD_MAX_FAILURES * 5

        def answer(_pair: str, n: int) -> MagicMock:
            if n > polls_while_running:
                return _response(body={"result": {"k": 1}})
            return _response(body={"job_id": "same-job"})

        out = self._run(["A", "B"], answer)
        self.assertEqual([], out["dropped"])

    def test_pair_that_keeps_returning_404_is_dropped(self) -> None:
        out = self._run(["A", "B"], lambda _p, _n: _response(status=404))
        self.assertEqual(["A->B", "B->A"], sorted(out["dropped"]))
        self.assertEqual(gap_analysis.PRELOAD_MAX_FAILURES, out["polls"]["A->B"])

    def test_job_that_keeps_failing_and_requeueing_is_dropped(self) -> None:
        # map_analysis enqueues a new job once the last one failed, so a changed
        # job id means the previous job ended without producing a result.
        out = self._run(["A", "B"], lambda p, n: _response(body={"job_id": f"{p}{n}"}))
        self.assertEqual(["A->B", "B->A"], sorted(out["dropped"]))
        # The first poll only records the job id, it is not a failure.
        self.assertEqual(gap_analysis.PRELOAD_MAX_FAILURES + 1, out["polls"]["A->B"])

    def test_failures_are_counted_per_pair(self) -> None:
        def answer(pair: str, _n: int) -> MagicMock:
            if pair == "A->B":
                return _response(status=404)
            return _response(body={"result": {"k": 1}})

        out = self._run(["A", "B"], answer)
        self.assertEqual(["A->B"], out["dropped"])

    def test_success_is_not_logged_when_pairs_were_dropped(self) -> None:
        with self.assertLogs(gap_analysis.logger, level="INFO") as logs:
            self._run(["A", "B"], lambda _p, _n: _response(status=404))
        self.assertFalse(any("preloaded successfully" in m for m in logs.output))
        self.assertTrue(any("A->B" in m and "ERROR" in m for m in logs.output))


if __name__ == "__main__":
    unittest.main()
