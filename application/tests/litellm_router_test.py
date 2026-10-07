from cre_logging import get_logger

logger = get_logger(__name__)

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from application.prompt_client import litellm_router, llm_error_utils, prompt_client


class _FakeEmbeddingsSingleton:
    def with_ai_client(self, ai_client):
        self.ai_client = ai_client
        return self


def _chat_resp(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class TestLiteLLMRouter(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("CRE_VALIDATE_EMBED_DIM_ON_INIT", None)

    def test_prompt_handler_uses_shared_router(self) -> None:
        os.environ["CRE_VALIDATE_EMBED_DIM_ON_INIT"] = "0"
        fake_embed_singleton = _FakeEmbeddingsSingleton()
        fake_db = Mock()
        fake_db.assert_embedding_contract = Mock()
        with patch(
            "application.prompt_client.prompt_client.in_memory_embeddings.instance",
            return_value=fake_embed_singleton,
        ):
            with patch("application.prompt_client.prompt_client.logger.info"):
                ph = prompt_client.PromptHandler(fake_db)
        self.assertIs(ph.ai_client, ph)
        self.assertIsNotNone(ph._litellm)

    def test_rate_limit_error_helper_detects_429(self) -> None:
        err = Exception("HTTP 429 too many requests")
        self.assertTrue(llm_error_utils.is_rate_limit_error(err))

    def test_rate_limit_error_helper_detects_quota_message(self) -> None:
        err = Exception("resource exhausted due to quota")
        self.assertTrue(llm_error_utils.is_rate_limit_error(err))

    def test_completion_retries_rate_limit_then_succeeds(self) -> None:
        client = Mock(
            completion=Mock(
                side_effect=[
                    Exception("HTTP 429 too many requests"),
                    _chat_resp("ok"),
                ]
            )
        )
        with patch("application.prompt_client.litellm_router.time.sleep"):
            resp = litellm_router.completion(
                model="gemini/gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
                client=client,
                max_retries=2,
                retry_sleep_seconds=0,
            )
        self.assertEqual(litellm_router.extract_content_text(resp), "ok")
        self.assertEqual(client.completion.call_count, 2)

    def test_system_user_fn_returns_assistant_text(self) -> None:
        client = Mock(completion=Mock(return_value=_chat_resp("cre-id")))
        with patch(
            "application.prompt_client.litellm_router.get_litellm",
            return_value=client,
        ):
            fn = litellm_router.system_user_fn("gemini/gemini-2.5-flash")
            self.assertEqual(fn("sys", "user"), "cre-id")

    def test_extract_content_text_lenient_on_empty(self) -> None:
        self.assertEqual(
            litellm_router.extract_content_text({}, strict=False),
            "",
        )


if __name__ == "__main__":
    unittest.main()
