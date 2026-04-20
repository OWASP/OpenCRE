import os
import unittest
from unittest.mock import patch

from application.validate_config import (
    validate_embeddings_config,
    validate_neo4j_config,
    validate_web_config,
)


class TestValidateWebConfig(unittest.TestCase):
    def test_skips_in_test_mode(self):
        """Should not call sys.exit in test or testing mode regardless of env vars."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"GOOGLE_CLIENT_SECRET": "", "GOOGLE_CLIENT_ID": ""}
        ):
            os.environ.pop("NO_LOGIN", None)
            validate_web_config("test")
            validate_web_config("testing")
        mock_exit.assert_not_called()

    def test_exits_when_auth_credentials_missing(self):
        """Should exit when NO_LOGIN is not set and Google credentials are absent."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"GOOGLE_CLIENT_SECRET": "", "GOOGLE_CLIENT_ID": ""}
        ):
            os.environ.pop("NO_LOGIN", None)
            validate_web_config("production")
        mock_exit.assert_called_once_with(1)

    def test_exits_when_only_secret_missing(self):
        """Should exit when GOOGLE_CLIENT_SECRET is absent even if GOOGLE_CLIENT_ID is set."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {"GOOGLE_CLIENT_SECRET": "", "GOOGLE_CLIENT_ID": "client-id"},
        ):
            os.environ.pop("NO_LOGIN", None)
            validate_web_config("production")
        mock_exit.assert_called_once_with(1)

    def test_skips_auth_check_when_no_login_set(self):
        """Should not exit when NO_LOGIN is set, even without Google credentials."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {
                "NO_LOGIN": "True",
                "GOOGLE_CLIENT_SECRET": "",
                "GOOGLE_CLIENT_ID": "",
            },
        ):
            validate_web_config("production")
        mock_exit.assert_not_called()

    def test_passes_with_full_credentials(self):
        """Should not exit when all required credentials are present."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_SECRET": "secret",
                "GOOGLE_CLIENT_ID": "client-id",
                "NEO4J_URL": "neo4j://localhost:7687",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            os.environ.pop("NO_LOGIN", None)
            validate_web_config("production")
        mock_exit.assert_not_called()

    def test_warns_but_does_not_exit_when_neo4j_missing(self):
        """Should warn but not exit when NEO4J_URL is absent."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {
                "NO_LOGIN": "True",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            os.environ.pop("NEO4J_URL", None)
            validate_web_config("production")
        mock_exit.assert_not_called()

    def test_warns_but_does_not_exit_when_redis_missing(self):
        """Should warn but not exit when REDIS_URL and REDIS_HOST are absent."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {
                "NO_LOGIN": "True",
                "NEO4J_URL": "neo4j://localhost:7687",
            },
        ):
            os.environ.pop("REDIS_URL", None)
            os.environ.pop("REDIS_HOST", None)
            validate_web_config("production")
        mock_exit.assert_not_called()


class TestValidateEmbeddingsConfig(unittest.TestCase):
    def test_exits_when_no_ai_provider_configured(self):
        """Should exit when none of OPENAI_API_KEY, GEMINI_API_KEY, or GCP_NATIVE is set."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GCP_NATIVE": ""},
        ):
            validate_embeddings_config()
        mock_exit.assert_called_once_with(1)

    def test_passes_with_openai_key(self):
        """Should not exit when OPENAI_API_KEY is set."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-test"}
        ):
            validate_embeddings_config()
        mock_exit.assert_not_called()

    def test_passes_with_gemini_key(self):
        """Should not exit when GEMINI_API_KEY is set."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"GEMINI_API_KEY": "key"}
        ):
            validate_embeddings_config()
        mock_exit.assert_not_called()

    def test_passes_with_gcp_native(self):
        """Should not exit when GCP_NATIVE is set."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"GCP_NATIVE": "true"}
        ):
            validate_embeddings_config()
        mock_exit.assert_not_called()


class TestValidateNeo4jConfig(unittest.TestCase):
    def test_exits_when_neo4j_url_missing(self):
        """Should exit when NEO4J_URL is not set."""
        with patch("sys.exit") as mock_exit, patch.dict(os.environ, {"NEO4J_URL": ""}):
            validate_neo4j_config()
        mock_exit.assert_called_once_with(1)

    def test_passes_when_neo4j_url_set(self):
        """Should not exit when NEO4J_URL is present."""
        with patch("sys.exit") as mock_exit, patch.dict(
            os.environ, {"NEO4J_URL": "neo4j://localhost:7687"}
        ):
            validate_neo4j_config()
        mock_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
