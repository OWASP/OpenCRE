from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import requests

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import ga_upstream_fetch
from application.utils.ga_upstream_fetch import (
    GaUpstreamError,
    GaUpstreamNotFound,
    fetch_ga_upstream_json,
    load_settings,
    resolve_gap_analysis_pair,
)

MODULE = "application.utils.ga_upstream_fetch"
GA_ELIGIBLE_TAGS = ["family:standard", "subtype:requirements_standard"]
MATERIAL_RESULT = {"node-a": {"start": {"name": "A"}, "paths": {}}}
STANDARDS = ["StandardA", "StandardB"]
CACHE_KEY = "StandardA >> StandardB"


def upstream_response(
    status_code: int,
    body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = body
    return response


class FakeRedis:
    """The two commands the in-flight lock uses, with SET NX semantics."""

    def __init__(self) -> None:
        self.keys: Dict[str, int] = {}

    def set(self, key: str, value: str, nx: bool, ex: int) -> Optional[bool]:
        if nx and key in self.keys:
            return None
        self.keys[key] = ex
        return True

    def delete(self, key: str) -> None:
        del self.keys[key]


class TestLoadSettings(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_env_defaults(self) -> None:
        settings = load_settings()

        self.assertEqual(settings.base_url, "https://opencre.org/rest/v1")
        self.assertEqual(settings.timeout_seconds, 30)
        self.assertEqual(settings.max_attempts, 4)
        self.assertEqual(settings.backoff_seconds, 2)
        self.assertGreaterEqual(settings.inflight_lock_ttl_seconds, 150)

    @patch.dict(
        os.environ,
        {
            "CRE_GA_UPSTREAM_API_URL": "http://upstream.test/rest/v1/",
            "CRE_GA_UPSTREAM_TIMEOUT_SECONDS": "5",
            "CRE_GA_UPSTREAM_MAX_ATTEMPTS": "2",
            "CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS": "0",
        },
        clear=True,
    )
    def test_env_overrides(self) -> None:
        settings = load_settings()

        self.assertEqual(settings.base_url, "http://upstream.test/rest/v1")
        self.assertEqual(settings.timeout_seconds, 5)
        self.assertEqual(settings.max_attempts, 2)
        self.assertEqual(settings.backoff_seconds, 0)

    def test_invalid_env_falls_back_to_defaults(self) -> None:
        for raw in ("abc", "0", "-1", "nan", "inf", " "):
            with self.subTest(raw=raw), patch.dict(
                os.environ,
                {
                    "CRE_GA_UPSTREAM_TIMEOUT_SECONDS": raw,
                    "CRE_GA_UPSTREAM_MAX_ATTEMPTS": raw,
                },
                clear=True,
            ):
                settings = load_settings()

                self.assertEqual(settings.timeout_seconds, 30)
                self.assertEqual(settings.max_attempts, 4)

    def test_does_not_read_upstream_sync_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CRE_UPSTREAM_API_URL": "http://graph-sync.test",
                "CRE_UPSTREAM_MAX_ATTEMPTS": "9",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.base_url, "https://opencre.org/rest/v1")
        self.assertEqual(settings.max_attempts, 4)


@patch.dict(os.environ, {}, clear=True)
@patch(f"{MODULE}.time.sleep")
@patch(f"{MODULE}.requests.get")
class TestFetchGaUpstreamJson(unittest.TestCase):
    def test_retries_transient_network_failure(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("reset by peer"),
            upstream_response(200, {"result": MATERIAL_RESULT}),
        ]

        payload = fetch_ga_upstream_json("/map_analysis")

        self.assertEqual(payload, {"result": MATERIAL_RESULT})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(2.0)

    def test_404_raises_not_found_without_retry(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = upstream_response(404)

        with self.assertRaises(GaUpstreamNotFound):
            fetch_ga_upstream_json("/map_analysis")

        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()

    def test_other_4xx_fails_without_retry(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = upstream_response(400)

        with self.assertRaises(GaUpstreamError) as caught:
            fetch_ga_upstream_json("/map_analysis")

        self.assertNotIsInstance(caught.exception, GaUpstreamNotFound)
        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()

    def test_5xx_retries_with_linear_backoff_until_exhausted(
        self, mock_get, mock_sleep
    ) -> None:
        mock_get.return_value = upstream_response(503)

        with self.assertRaises(GaUpstreamError):
            fetch_ga_upstream_json("/map_analysis")

        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [2, 4, 6])

    def test_429_honors_retry_after(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            upstream_response(429, headers={"Retry-After": "7"}),
            upstream_response(200, {"result": MATERIAL_RESULT}),
        ]

        fetch_ga_upstream_json("/map_analysis")

        mock_sleep.assert_called_once_with(7.0)

    def test_retry_after_is_capped_by_the_timeout(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            upstream_response(429, headers={"Retry-After": "3600"}),
            upstream_response(200, {"result": MATERIAL_RESULT}),
        ]

        fetch_ga_upstream_json("/map_analysis")

        mock_sleep.assert_called_once_with(30.0)

    def test_malformed_retry_after_keeps_a_valid_delay(
        self, mock_get, mock_sleep
    ) -> None:
        for retry_after, expected in (
            ("Wed, 21 Oct 2026 07:28:00 GMT", 2.0),
            ("-5", 0.0),
            ("nan", 0.0),
        ):
            with self.subTest(retry_after=retry_after):
                mock_sleep.reset_mock()
                mock_get.side_effect = [
                    upstream_response(429, headers={"Retry-After": retry_after}),
                    upstream_response(200, {"result": MATERIAL_RESULT}),
                ]

                fetch_ga_upstream_json("/map_analysis")

                mock_sleep.assert_called_once_with(expected)

    def test_invalid_json_is_retried_then_fails(self, mock_get, mock_sleep) -> None:
        response = upstream_response(200)
        response.json.side_effect = requests.exceptions.JSONDecodeError("bad", "", 0)
        mock_get.return_value = response

        with self.assertRaises(GaUpstreamError):
            fetch_ga_upstream_json("/map_analysis")

        self.assertEqual(mock_get.call_count, 4)

    def test_non_object_json_fails(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = upstream_response(200, ["not", "an", "object"])

        with self.assertRaises(GaUpstreamError):
            fetch_ga_upstream_json("/map_analysis")

    def test_uses_configured_base_url_and_timeout(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = upstream_response(200, {})
        params = [("standard", "A & B"), ("standard", "C")]

        with patch.dict(
            os.environ,
            {
                "CRE_GA_UPSTREAM_API_URL": "http://upstream.test/rest/v1",
                "CRE_GA_UPSTREAM_TIMEOUT_SECONDS": "5",
            },
        ):
            fetch_ga_upstream_json("/map_analysis", params=params)

        mock_get.assert_called_once_with(
            "http://upstream.test/rest/v1/map_analysis", params=params, timeout=5.0
        )


class TestResolveGapAnalysisPair(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        sleep = patch(f"{MODULE}.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        http_get = patch(f"{MODULE}.requests.get")
        self.mock_get = http_get.start()
        self.addCleanup(http_get.stop)
        # Without a reachable Redis the in-process lock applies; tests that
        # exercise the Redis lock install a FakeRedis instead.
        redis_connect = patch(f"{MODULE}.redis.connect")
        self.mock_connect = redis_connect.start()
        self.mock_connect.side_effect = ConnectionError("no redis")
        self.addCleanup(redis_connect.stop)

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def _stored_row(self) -> Optional[str]:
        return self.collection.get_gap_analysis_result(cache_key=CACHE_KEY)

    def _seed_material_row(self) -> str:
        ga_object = json.dumps({"result": {"local": {"paths": {}}}})
        self.collection.add_gap_analysis_result(CACHE_KEY, ga_object)
        return ga_object

    def _add_standard(self, name: str, tags: Any) -> None:
        self.collection.add_node(defs.Standard(name=name, section="s", tags=tags))

    def _assert_lock_released(self) -> None:
        self.mock_get.reset_mock()
        self.mock_get.return_value = upstream_response(404)
        self.mock_get.side_effect = None
        self.assertEqual(
            resolve_gap_analysis_pair(STANDARDS, self.collection).status_code, 404
        )
        self.mock_get.assert_called_once()

    def test_fetch_success_upserts_material_row(self) -> None:
        self.mock_get.return_value = upstream_response(
            200, {"result": MATERIAL_RESULT, "ignored": True}
        )

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(resolution.payload, {"result": MATERIAL_RESULT})
        self.assertEqual(json.loads(self._stored_row()), {"result": MATERIAL_RESULT})
        self.assertTrue(self.collection.gap_analysis_exists(CACHE_KEY))
        self.mock_get.assert_called_once_with(
            "https://opencre.org/rest/v1/map_analysis",
            params=[("standard", "StandardA"), ("standard", "StandardB")],
            timeout=30.0,
        )

    def test_success_logs_upstream_pull(self) -> None:
        self.mock_get.return_value = upstream_response(200, {"result": MATERIAL_RESULT})

        with self.assertLogs(MODULE, level="INFO") as logs:
            resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertIn(
            "GA upstream fetch: pulled pair StandardA >> StandardB "
            "from https://opencre.org/rest/v1",
            "\n".join(logs.output),
        )

    def test_read_only_get(self) -> None:
        self.mock_get.return_value = upstream_response(200, {"result": MATERIAL_RESULT})

        with patch(f"{MODULE}.requests.post") as post, patch(
            f"{MODULE}.requests.put"
        ) as put, patch(f"{MODULE}.requests.patch") as patch_, patch(
            f"{MODULE}.requests.delete"
        ) as delete:
            resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.mock_get.assert_called_once()
        for method in (post, put, patch_, delete):
            method.assert_not_called()

    def test_v1_no_refetch(self) -> None:
        self.mock_get.return_value = upstream_response(200, {"result": MATERIAL_RESULT})

        first = resolve_gap_analysis_pair(STANDARDS, self.collection)
        second = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(second, first)
        self.mock_get.assert_called_once()

    def test_cached_pair_never_calls_upstream_or_locks(self) -> None:
        ga_object = self._seed_material_row()

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(resolution.payload, json.loads(ga_object))
        self.mock_get.assert_not_called()
        self.mock_connect.assert_not_called()

    def test_pair_cached_while_taking_the_lock_is_not_fetched(self) -> None:
        def backfill_then_fail(*_: Any, **__: Any) -> None:
            self._seed_material_row()
            raise ConnectionError("no redis")

        self.mock_connect.side_effect = backfill_then_fail

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)
        self.mock_get.assert_not_called()

    def test_fetch_404_no_upsert(self) -> None:
        self.mock_get.return_value = upstream_response(404)

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 404)
        self.assertEqual(resolution.payload["error_code"], "ga_cache_miss")
        self.assertFalse(resolution.payload["try_again"])
        self.assertIn("backfill_docs_url", resolution.payload)
        self.assertIsNone(self._stored_row())
        self.mock_get.assert_called_once()

    def test_prod_down_try_again(self) -> None:
        self.mock_get.side_effect = requests.exceptions.ConnectionError("secret-host")

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 503)
        self.assertEqual(resolution.payload["error_code"], "ga_upstream_unavailable")
        self.assertTrue(resolution.payload["try_again"])
        self.assertIn("backfill_docs_url", resolution.payload)
        self.assertNotIn("secret-host", json.dumps(resolution.payload))
        self.assertIsNone(self._stored_row())
        self.assertEqual(self.mock_get.call_count, 4)

    def test_prod_down_serves_local_cache(self) -> None:
        ga_object = json.dumps({"result": MATERIAL_RESULT})

        def backfill_then_fail(*_: Any, **__: Any) -> None:
            self.collection.add_gap_analysis_result(CACHE_KEY, ga_object)
            raise requests.exceptions.ConnectionError("down")

        self.mock_get.side_effect = backfill_then_fail

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(resolution.payload, {"result": MATERIAL_RESULT})
        self.assertEqual(self._stored_row(), ga_object)

    def test_failed_fetch_preserves_cache(self) -> None:
        # A row only reaches the fetch path when it is not material.
        placeholder = '{"result": {}}'
        sqla.session.add(
            db.GapAnalysisResults(cache_key=CACHE_KEY, ga_object=placeholder)
        )
        sqla.session.commit()

        for bad_upstream in (
            upstream_response(200, {"result": {}}),
            upstream_response(200, {"job_id": "1234"}),
            upstream_response(202, {"status": "in_progress"}),
            upstream_response(500),
            upstream_response(404),
        ):
            with self.subTest(status=bad_upstream.status_code):
                self.mock_get.return_value = bad_upstream

                resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

                self.assertNotEqual(resolution.status_code, 200)
                self.assertEqual(self._stored_row(), placeholder)

    def test_non_material_upstream_answer_keeps_material_row(self) -> None:
        ga_object = json.dumps({"result": MATERIAL_RESULT})

        def backfill_then_answer_empty(*_: Any, **__: Any) -> Mock:
            self.collection.add_gap_analysis_result(CACHE_KEY, ga_object)
            return upstream_response(200, {"result": {}})

        self.mock_get.side_effect = backfill_then_answer_empty

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(resolution.payload, {"result": MATERIAL_RESULT})
        self.assertEqual(self._stored_row(), ga_object)

    def test_no_upstream_flag_skips_http(self) -> None:
        for value in ("1", "true", "YES"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CRE_GA_NO_UPSTREAM": value}
            ):
                resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

                self.assertEqual(resolution.status_code, 404)
                self.assertEqual(resolution.payload["error_code"], "ga_cache_miss")
                self.assertFalse(resolution.payload["soft_cta"]["show"])
                self.mock_get.assert_not_called()

    def test_no_upstream_flag_off_values_still_fetch(self) -> None:
        self.mock_get.return_value = upstream_response(404)

        for value in ("", "0", "false"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CRE_GA_NO_UPSTREAM": value}
            ):
                self.mock_get.reset_mock()
                resolve_gap_analysis_pair(STANDARDS, self.collection)
                self.mock_get.assert_called_once()

    def test_no_upstream_flag_still_serves_cache(self) -> None:
        self._seed_material_row()

        with patch.dict(os.environ, {"CRE_GA_NO_UPSTREAM": "1"}):
            resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)

    def _assert_concurrent_request_is_in_progress(self) -> None:
        nested = []

        def resolve_again_during_fetch(*_: Any, **__: Any) -> Mock:
            nested.append(resolve_gap_analysis_pair(STANDARDS, self.collection))
            return upstream_response(200, {"result": MATERIAL_RESULT})

        self.mock_get.side_effect = resolve_again_during_fetch

        first = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.mock_get.call_count, 1)
        self.assertEqual(nested[0].status_code, 202)
        self.assertEqual(
            nested[0].payload,
            {"status": "in_progress", "cache_key": CACHE_KEY, "poll_after_seconds": 2},
        )

    def test_concurrent_in_progress_with_local_lock(self) -> None:
        self._assert_concurrent_request_is_in_progress()

    def test_concurrent_in_progress_with_redis_lock(self) -> None:
        fake_redis = FakeRedis()
        self.mock_connect.side_effect = None
        self.mock_connect.return_value = fake_redis

        self._assert_concurrent_request_is_in_progress()

        self.assertEqual(fake_redis.keys, {})

    def test_redis_lock_namespace_and_ttl(self) -> None:
        fake_redis = FakeRedis()
        self.mock_connect.side_effect = None
        self.mock_connect.return_value = fake_redis
        seen = {}

        def capture_lock(*_: Any, **__: Any) -> Mock:
            seen.update(fake_redis.keys)
            return upstream_response(404)

        self.mock_get.side_effect = capture_lock

        resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(list(seen), [f"ga:upstream:inflight:{CACHE_KEY}"])
        self.assertEqual(
            seen[f"ga:upstream:inflight:{CACHE_KEY}"],
            load_settings().inflight_lock_ttl_seconds,
        )

    def test_lock_released_after_each_failure(self) -> None:
        fake_redis = FakeRedis()
        for use_redis in (False, True):
            if use_redis:
                self.mock_connect.side_effect = None
                self.mock_connect.return_value = fake_redis
            for failure in (
                upstream_response(404),
                requests.exceptions.ConnectionError("down"),
                upstream_response(200, {"job_id": "1234"}),
            ):
                with self.subTest(use_redis=use_redis, failure=failure):
                    self.mock_get.side_effect = [failure] * 4

                    resolve_gap_analysis_pair(STANDARDS, self.collection)

                    self.assertEqual(fake_redis.keys, {})
                    self._assert_lock_released()

    def test_lock_released_when_upsert_raises(self) -> None:
        self.mock_get.return_value = upstream_response(200, {"result": MATERIAL_RESULT})

        with patch.object(
            self.collection,
            "add_gap_analysis_result",
            side_effect=RuntimeError("db down"),
        ), self.assertRaises(RuntimeError):
            resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(ga_upstream_fetch._local_inflight, set())

    def test_failing_lock_release_does_not_hide_the_result(self) -> None:
        fake_redis = FakeRedis()
        fake_redis.delete = Mock(side_effect=ConnectionError("redis went away"))
        self.mock_connect.side_effect = None
        self.mock_connect.return_value = fake_redis
        self.mock_get.return_value = upstream_response(200, {"result": MATERIAL_RESULT})

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.status_code, 200)

    def test_soft_cta_positive(self) -> None:
        self._add_standard("StandardA", GA_ELIGIBLE_TAGS)
        self._add_standard("StandardB", GA_ELIGIBLE_TAGS)

        for upstream, status_code in (
            (upstream_response(404), 404),
            (upstream_response(500), 503),
        ):
            with self.subTest(status_code=status_code):
                self.mock_get.return_value = upstream

                resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

                self.assertEqual(resolution.status_code, status_code)
                soft_cta = resolution.payload["soft_cta"]
                self.assertTrue(soft_cta["show"])
                self.assertIn("filing an issue", soft_cta["message"])
                self.assertEqual(
                    soft_cta["issue_url"], "https://github.com/OWASP/OpenCRE/issues/new"
                )

    def test_soft_cta_negative_missing_standard(self) -> None:
        self._add_standard("StandardA", GA_ELIGIBLE_TAGS)
        self.mock_get.return_value = upstream_response(404)

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.payload["soft_cta"], {"show": False})

    def test_soft_cta_negative_non_participant(self) -> None:
        self._add_standard("StandardA", GA_ELIGIBLE_TAGS)
        self._add_standard("StandardB", ["family:standard"])
        self.mock_get.return_value = upstream_response(404)

        resolution = resolve_gap_analysis_pair(STANDARDS, self.collection)

        self.assertEqual(resolution.payload["soft_cta"], {"show": False})


if __name__ == "__main__":
    unittest.main()
