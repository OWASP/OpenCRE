import os
import unittest
from unittest import mock

from application.prompt_client import litellm_router as lr
from application.prompt_client.llm_error_utils import (
    is_overload_error,
    is_transient_llm_error,
)


class ServiceUnavailableError(Exception):
    pass


class AuthenticationError(Exception):
    pass


def ok(text="hi"):
    msg = mock.Mock(content=text)
    return mock.Mock(choices=[mock.Mock(message=msg)])


class ClassifierTest(unittest.TestCase):
    def test_provider_outages_are_transient(self):
        for err in (
            ServiceUnavailableError(
                "GeminiException - The model is overloaded. high demand"
            ),
            RuntimeError("503 Service Unavailable"),
            RuntimeError('{"error": {"code": 503, "message": "x"}}'),
            RuntimeError("Internal error encountered"),
            TimeoutError("timed out"),
        ):
            self.assertTrue(is_transient_llm_error(err), err)
        self.assertTrue(is_overload_error(ServiceUnavailableError("x")))

    def test_bad_key_or_request_is_not_transient(self):
        self.assertFalse(
            is_transient_llm_error(AuthenticationError("API key not valid"))
        )
        self.assertFalse(is_transient_llm_error(ValueError("bad request")))


class ResilientCompletionTest(unittest.TestCase):
    def setUp(self):
        lr.reset_breaker()
        env = mock.patch.dict(
            os.environ,
            {
                "LLM_INTERACTIVE_RETRIES": "2",
                "LLM_INTERACTIVE_BASE_DELAY": "0.01",
                "LLM_BREAKER_FAILURES": "2",
                "LLM_BREAKER_COOLDOWN_SECONDS": "60",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        sleeper = mock.patch("time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def _client(self, behaviour):
        client = mock.Mock()
        client.completion.side_effect = behaviour
        return client

    def test_recovers_from_a_short_outage_without_fallback(self):
        calls = []

        def behaviour(model, messages, **kw):
            calls.append(model)
            if len(calls) < 3:
                raise ServiceUnavailableError("503 overloaded")
            return ok("answer")

        out = lr.resilient_completion(
            model="m1",
            fallback_model="m2",
            messages=[{"role": "user", "content": "q"}],
            client=self._client(behaviour),
        )
        self.assertEqual(lr.extract_content_text(out), "answer")
        self.assertEqual(
            calls, ["m1", "m1", "m1"]
        )  # same model after two quick retries

    def test_falls_back_when_the_primary_stays_down(self):
        def behaviour(model, messages, **kw):
            if model == "m1":
                raise ServiceUnavailableError("503 overloaded")
            return ok("from fallback")

        out = lr.resilient_completion(
            model="m1", fallback_model="m2", messages=[], client=self._client(behaviour)
        )
        self.assertEqual(lr.extract_content_text(out), "from fallback")

    def test_non_transient_errors_do_not_retry_or_fall_back(self):
        client = self._client(AuthenticationError("API key not valid"))
        with self.assertRaises(AuthenticationError):
            lr.resilient_completion(
                model="m1", fallback_model="m2", messages=[], client=client
            )
        self.assertEqual(client.completion.call_count, 1)

    def test_breaker_skips_the_failing_primary_after_repeated_failures(self):
        seen = []

        def behaviour(model, messages, **kw):
            seen.append(model)
            if model == "m1":
                raise ServiceUnavailableError("503")
            return ok("fb")

        client = self._client(behaviour)
        for _ in range(2):  # two full failures open the breaker (threshold 2)
            lr.resilient_completion(
                model="m1", fallback_model="m2", messages=[], client=client
            )
        seen.clear()
        lr.resilient_completion(
            model="m1", fallback_model="m2", messages=[], client=client
        )
        self.assertEqual(seen, ["m2"])  # straight to the fallback

    def test_without_a_fallback_an_outage_is_raised(self):
        client = self._client(ServiceUnavailableError("503"))
        with self.assertRaises(ServiceUnavailableError):
            lr.resilient_completion(model="m1", messages=[], client=client)

    def test_quick_retry_helper_for_embeddings(self):
        n = {"i": 0}

        def flaky():
            n["i"] += 1
            if n["i"] < 3:
                raise RuntimeError("503 Service Unavailable")
            return [0.1]

        self.assertEqual(lr.quick_retry(flaky, context="t"), [0.1])
