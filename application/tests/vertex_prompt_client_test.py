"""Tests for Gemini retry helpers and rate-limit detection."""

import os
import unittest

from google.genai import errors as genai_errors

from application.prompt_client.vertex_prompt_client import (
    _effective_gemini_generate_retry_settings,
    _effective_vertex_embed_retry_settings,
    _is_genai_rate_limit_error,
    _is_heroku_web_dyno,
)


class TestVertexPromptClientHelpers(unittest.TestCase):
    def tearDown(self) -> None:
        for key in (
            "DYNO",
            "GEMINI_GENERATE_MAX_RETRIES",
            "GEMINI_GENERATE_RETRY_SLEEP_SECONDS",
            "VERTEX_EMBED_MAX_RETRIES",
            "VERTEX_EMBED_RETRY_SLEEP_SECONDS",
        ):
            os.environ.pop(key, None)

    def test_is_heroku_web_dyno_true_for_web_prefix(self) -> None:
        os.environ["DYNO"] = "web.1"
        self.assertTrue(_is_heroku_web_dyno())

    def test_is_heroku_web_dyno_true_case_insensitive(self) -> None:
        os.environ["DYNO"] = "Web.1"
        self.assertTrue(_is_heroku_web_dyno())

    def test_is_heroku_web_dyno_false_for_worker(self) -> None:
        os.environ["DYNO"] = "worker.1"
        self.assertFalse(_is_heroku_web_dyno())

    def test_is_heroku_web_dyno_false_when_unset(self) -> None:
        self.assertFalse(_is_heroku_web_dyno())

    def test_effective_gemini_retry_defaults_local(self) -> None:
        self.assertEqual(_effective_gemini_generate_retry_settings(), (3, 60))

    def test_effective_gemini_retry_defaults_heroku_web(self) -> None:
        os.environ["DYNO"] = "web.1"
        self.assertEqual(_effective_gemini_generate_retry_settings(), (0, 0))

    def test_effective_gemini_retry_env_overrides_heroku(self) -> None:
        os.environ["DYNO"] = "web.1"
        os.environ["GEMINI_GENERATE_MAX_RETRIES"] = "2"
        os.environ["GEMINI_GENERATE_RETRY_SLEEP_SECONDS"] = "10"
        self.assertEqual(_effective_gemini_generate_retry_settings(), (2, 10))

    def test_effective_embed_retry_defaults_local(self) -> None:
        self.assertEqual(_effective_vertex_embed_retry_settings(), (3, 60))

    def test_effective_embed_retry_defaults_heroku_web(self) -> None:
        os.environ["DYNO"] = "web.1"
        self.assertEqual(_effective_vertex_embed_retry_settings(), (0, 0))

    def test_is_genai_rate_limit_error_recognizes_clienterror_code_429(self) -> None:
        err = genai_errors.ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "message": "Resource exhausted",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
            None,
        )
        self.assertTrue(_is_genai_rate_limit_error(err))

    def test_is_genai_rate_limit_error_false_for_other_clienterror(self) -> None:
        err = genai_errors.ClientError(
            400,
            {
                "error": {
                    "code": 400,
                    "message": "Bad request",
                    "status": "INVALID_ARGUMENT",
                }
            },
            None,
        )
        self.assertFalse(_is_genai_rate_limit_error(err))


if __name__ == "__main__":
    unittest.main()
