"""Tests for /rest/v1/completion (chatbot) error handling."""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import unittest
from unittest.mock import patch

from google.genai import errors as genai_errors

from application import create_app, sqla  # type: ignore


class TestChatCompletion(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        os.environ.pop("NO_LOGIN", None)

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        os.environ["INSECURE_REQUESTS"] = "True"
        sqla.create_all()

    def test_completion_returns_503_json_on_gemini_429(self) -> None:
        os.environ["NO_LOGIN"] = "1"
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
        with patch("application.prompt_client.prompt_client.PromptHandler") as mock_ph:
            mock_ph.return_value.generate_text.side_effect = err
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "test"},
                    content_type="application/json",
                )
        self.assertEqual(503, response.status_code)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("rate-limited", data["error"])

    def test_completion_returns_provider_status_on_non_429_genai_error(self) -> None:
        os.environ["NO_LOGIN"] = "1"
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
        with patch("application.prompt_client.prompt_client.PromptHandler") as mock_ph:
            mock_ph.return_value.generate_text.side_effect = err
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "test"},
                    content_type="application/json",
                )
        self.assertEqual(400, response.status_code)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("AI Service Error", data["error"])

    def test_completion_returns_503_when_prompt_client_import_fails(self) -> None:
        os.environ["NO_LOGIN"] = "1"
        with patch(
            "application.prompt_client.prompt_client.PromptHandler",
            side_effect=ImportError("nltk"),
        ):
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "test"},
                    content_type="application/json",
                )
        self.assertEqual(503, response.status_code)

    def test_completion_returns_503_when_litellm_missing(self) -> None:
        os.environ["NO_LOGIN"] = "1"
        with patch(
            "application.prompt_client.prompt_client.PromptHandler",
            side_effect=RuntimeError("litellm package is required for PromptHandler"),
        ):
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "test"},
                    content_type="application/json",
                )
        self.assertEqual(503, response.status_code)

    def test_completion_propagates_unrelated_runtime_error(self) -> None:
        os.environ["NO_LOGIN"] = "1"
        with patch(
            "application.prompt_client.prompt_client.PromptHandler",
            side_effect=RuntimeError("database exploded"),
        ):
            with self.app.test_client() as client:
                with self.assertRaises(RuntimeError):
                    client.post(
                        "/rest/v1/completion",
                        json={"prompt": "test"},
                        content_type="application/json",
                    )

    def test_completion_passes_messages_history_to_generate_text(self) -> None:
        os.environ["NO_LOGIN"] = "1"
        os.environ["OWASP_AGENT_ENABLED"] = "0"
        with patch("application.prompt_client.prompt_client.PromptHandler") as mock_ph:
            mock_ph.return_value.generate_text.return_value = {
                "response": "Answer: ok",
                "table": [],
                "accurate": True,
                "model_name": "test-llm",
            }
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={
                        "prompt": "and in Morocco?",
                        "messages": [
                            {
                                "role": "user",
                                "content": "OWASP membership cost in Switzerland?",
                            },
                            {"role": "assistant", "content": "Answer: standard dues"},
                            {"role": "user", "content": "and in Morocco?"},
                        ],
                    },
                    content_type="application/json",
                )
        self.assertEqual(200, response.status_code)
        kwargs = mock_ph.return_value.generate_text.call_args
        # positional prompt + history kw
        self.assertEqual(kwargs.args[0], "and in Morocco?")
        history = kwargs.kwargs.get("history")
        self.assertIsNotNone(history)
        assert history is not None
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("Switzerland", history[0]["content"])
        self.assertEqual(history[-1]["role"], "assistant")
        os.environ.pop("OWASP_AGENT_ENABLED", None)


class TestChatHistoryHelpers(unittest.TestCase):
    def test_split_prompt_strips_trailing_user_duplicate(self) -> None:
        from application.utils.chat_history import split_prompt_and_history

        prompt, history = split_prompt_and_history(
            {
                "prompt": "follow up",
                "messages": [
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "Answer: hi"},
                    {"role": "user", "content": "follow up"},
                ],
            }
        )
        self.assertEqual(prompt, "follow up")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["content"], "first")


if __name__ == "__main__":
    unittest.main()
