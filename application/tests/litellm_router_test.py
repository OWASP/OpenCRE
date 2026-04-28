import os
import unittest
from unittest.mock import Mock, patch

from application.prompt_client import llm_error_utils, prompt_client


class _FakeEmbeddingsSingleton:
    def with_ai_client(self, ai_client):
        self.ai_client = ai_client
        return self


class TestLiteLLMRouter(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("CRE_VALIDATE_EMBED_DIM_ON_INIT", None)

    def test_prompt_handler_uses_litellm_directly(self) -> None:
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

    def test_rate_limit_error_helper_detects_429(self) -> None:
        err = Exception("HTTP 429 too many requests")
        self.assertTrue(llm_error_utils.is_rate_limit_error(err))

    def test_rate_limit_error_helper_detects_quota_message(self) -> None:
        err = Exception("resource exhausted due to quota")
        self.assertTrue(llm_error_utils.is_rate_limit_error(err))


if __name__ == "__main__":
    unittest.main()
