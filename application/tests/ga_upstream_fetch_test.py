import json
import logging
import os
import unittest
from unittest.mock import MagicMock, call, patch

import requests

from application.utils import ga_upstream_fetch


class MockResponse:
    def __init__(
        self,
        status_code: int,
        json_data: dict = None,
        headers: dict = None,
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data


class GaUpstreamFetchTest(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.gap_analysis_exists.return_value = False
        self.db.get_gap_analysis_result.return_value = None

        # Clean environment before each test
        for var in [
            "CRE_GA_NO_UPSTREAM",
            "CRE_GA_UPSTREAM_API_URL",
            "CRE_GA_UPSTREAM_TIMEOUT_SECONDS",
            "CRE_GA_UPSTREAM_MAX_ATTEMPTS",
            "CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS",
        ]:
            if var in os.environ:
                del os.environ[var]

    def test_env_defaults(self):
        """Unset env -> timeout 30, max_attempts 4."""
        session = MagicMock()
        session.get.return_value = MockResponse(
            200, {"result": {"some": "data", "links": [1]}}
        )

        ga_upstream_fetch.fetch_ga_upstream_json(
            ["Standard A", "Standard B"], session=session
        )

        session.get.assert_called_once()
        _, kwargs = session.get.call_args
        self.assertEqual(kwargs.get("timeout"), 30.0)

    def test_fetch_success_upserts_material_row(self):
        """Mock prod 200 -> add_gap_analysis_result called once with material JSON."""
        session = MagicMock()
        material_result = {"header": "test", "links": [{"id": 1}]}
        session.get.return_value = MockResponse(
            200, {"result": material_result}
        )

        with patch(
            "application.utils.gap_analysis.primary_gap_analysis_payload_is_material",
            return_value=True,
        ):
            status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
                ["Standard A", "Standard B"], self.db, session=session
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(body, {"result": material_result})
        self.db.add_gap_analysis_result.assert_called_once()
        call_kwargs = self.db.add_gap_analysis_result.call_args[1]
        self.assertIn("Standard A >> Standard B", call_kwargs["cache_key"])
        stored_obj = json.loads(call_kwargs["ga_object"])
        self.assertEqual(stored_obj["result"], material_result)

    def test_fetch_404_no_upsert(self):
        """Mock prod 404 -> no DB write; error dict returned."""
        session = MagicMock()
        session.get.return_value = MockResponse(404)

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 404)
        self.assertEqual(body["error_code"], "ga_cache_miss")
        self.assertFalse(body["try_again"])
        self.db.add_gap_analysis_result.assert_not_called()

    def test_fetch_404_no_retry(self):
        """Mock prod 404 -> HTTP call count = 1."""
        session = MagicMock()
        session.get.return_value = MockResponse(404)

        _, status, _ = ga_upstream_fetch.fetch_ga_upstream_json(
            ["Standard A", "Standard B"], session=session
        )

        self.assertEqual(status, 404)
        self.assertEqual(session.get.call_count, 1)

    def test_no_upstream_flag_skips_http(self):
        """CRE_GA_NO_UPSTREAM=1 -> zero HTTP calls."""
        os.environ["CRE_GA_NO_UPSTREAM"] = "1"
        session = MagicMock()

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 404)
        self.assertEqual(body["error_code"], "ga_cache_miss")
        self.assertEqual(session.get.call_count, 0)

    def test_v1_no_refetch(self):
        """Pre-seeded cache -> resolve -> HTTP mock not called."""
        self.db.gap_analysis_exists.return_value = True
        cached_result = {"header": "already cached", "items": [1]}
        self.db.get_gap_analysis_result.return_value = json.dumps(
            {"result": cached_result}
        )

        session = MagicMock()
        with patch(
            "application.utils.gap_analysis.primary_gap_analysis_payload_is_material",
            return_value=True,
        ):
            status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
                ["Standard A", "Standard B"], self.db, session=session
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(body, {"result": cached_result})
        self.assertEqual(session.get.call_count, 0)

    @patch("time.sleep", return_value=None)
    def test_prod_down_serves_local_cache(self, _mock_sleep):
        """Mock ConnectionError after retries + local row exists -> 200 from cache."""
        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        cached_result = {"header": "stale cached", "items": [2]}

        def fake_gap_analysis_exists(key):
            return True

        self.db.gap_analysis_exists.side_effect = fake_gap_analysis_exists
        # Simulate initial check missing or non-material, but local row available as fallback
        self.db.get_gap_analysis_result.return_value = json.dumps(
            {"result": cached_result}
        )

        with patch(
            "application.utils.gap_analysis.primary_gap_analysis_payload_is_material",
            side_effect=[False, True],
        ):
            status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
                ["Standard A", "Standard B"], self.db, session=session
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(body, {"result": cached_result})

    @patch("time.sleep", return_value=None)
    def test_prod_down_try_again(self, _mock_sleep):
        """Mock ConnectionError + no local row -> 503 and try_again: true."""
        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 503)
        self.assertEqual(body["error_code"], "ga_upstream_unavailable")
        self.assertTrue(body["try_again"])

    @patch("time.sleep", return_value=None)
    def test_failed_fetch_preserves_cache(self, _mock_sleep):
        """Bad prod response does not overwrite cache."""
        session = MagicMock()
        session.get.return_value = MockResponse(500)

        status_code, _ = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.db.add_gap_analysis_result.assert_not_called()

    def test_concurrent_in_progress(self):
        """When in-flight lock exists, returns 202 in_progress."""
        session = MagicMock()
        cache_key = "Standard A >> Standard B"
        ga_upstream_fetch._IN_FLIGHT_KEYS.add(cache_key)
        try:
            status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
                ["Standard A", "Standard B"], self.db, session=session
            )
            self.assertEqual(status_code, 202)
            self.assertEqual(body["status"], "in_progress")
            self.assertEqual(body["cache_key"], cache_key)
            self.assertEqual(session.get.call_count, 0)
        finally:
            ga_upstream_fetch._IN_FLIGHT_KEYS.discard(cache_key)

    def test_soft_cta_positive(self):
        """Both standards local + GA-eligible + prod 404 -> soft_cta.show: true."""
        session = MagicMock()
        session.get.return_value = MockResponse(404)

        self.db.get_node.return_value = MagicMock()
        self.db.get_ga_standards.return_value = [
            "Standard A",
            "Standard B",
            "Standard C",
        ]

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 404)
        self.assertIn("soft_cta", body)
        self.assertTrue(body["soft_cta"]["show"])

    def test_soft_cta_negative_missing_standard(self):
        """One standard missing locally -> soft_cta.show: false."""
        session = MagicMock()
        session.get.return_value = MockResponse(404)

        # First standard exists, second does not
        self.db.get_node.side_effect = [MagicMock(), None]
        self.db.get_ga_standards.return_value = ["Standard A", "Standard B"]

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 404)
        self.assertNotIn("soft_cta", body)

    def test_soft_cta_negative_non_participant(self):
        """Standard not in ga_standards -> soft_cta.show: false."""
        session = MagicMock()
        session.get.return_value = MockResponse(404)

        self.db.get_node.return_value = MagicMock()
        self.db.get_ga_standards.return_value = ["Standard C", "Standard D"]

        status_code, body = ga_upstream_fetch.resolve_gap_analysis_pair(
            ["Standard A", "Standard B"], self.db, session=session
        )

        self.assertEqual(status_code, 404)
        self.assertNotIn("soft_cta", body)

    def test_success_logs_upstream_pull(self):
        """Successful pull logs INFO line."""
        session = MagicMock()
        session.get.return_value = MockResponse(
            200, {"result": {"header": "foo", "links": [1]}}
        )

        with self.assertLogs("application.utils.ga_upstream_fetch", level="INFO") as cm:
            with patch(
                "application.utils.gap_analysis.primary_gap_analysis_payload_is_material",
                return_value=True,
            ):
                ga_upstream_fetch.resolve_gap_analysis_pair(
                    ["Standard A", "Standard B"], self.db, session=session
                )

        self.assertTrue(any("GA upstream fetch: pulled pair" in line for line in cm.output))

    def test_read_only_get(self):
        """Ensure client only calls GET, never POST/PUT/DELETE."""
        session = MagicMock()
        session.get.return_value = MockResponse(200, {"result": {}})

        ga_upstream_fetch.fetch_ga_upstream_json(
            ["Standard A", "Standard B"], session=session
        )

        session.get.assert_called_once()
        session.post.assert_not_called()
        session.put.assert_not_called()
        session.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
