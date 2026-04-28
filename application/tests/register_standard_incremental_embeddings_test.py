import os
import unittest
from unittest.mock import Mock, patch

from application import create_app, sqla  # type: ignore
from application.cmd import cre_main as main
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils import redis


class TestRegisterStandardIncrementalEmbeddings(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(prompt_client.in_memory_embeddings, "setup_playwright")
    @patch.object(prompt_client.in_memory_embeddings, "teardown_playwright")
    @patch.object(prompt_client.PromptHandler, "_litellm_get_text_embeddings")
    @patch.object(redis, "connect")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"})
    def test_register_standard_skips_reembedding_unchanged_node_content(
        self,
        redis_connect_mock,
        mock_get_text_embeddings,
        _mock_teardown_playwright,
        _mock_setup_playwright,
    ) -> None:
        """
        Step 4d integration:
        Re-registering the same standard twice should not invoke the embedding provider
        the second time (content unchanged -> embeddings_content cache hit).
        """
        redis_connect_mock.return_value = Mock(get=Mock(return_value=None), set=Mock())

        # Provider returns one embedding vector for the single text input.
        mock_get_text_embeddings.return_value = [[0.1, 0.2]]

        std = defs.Standard(
            name="ISO 27001",
            section="Policies",
            sectionID="5.10",
            subsection="",
            hyperlink="",
            tags=["family:standard", "subtype:requirements_standard"],
        )

        main.register_standard(
            standard_entries=[std],
            collection=self.collection,
            calculate_gap_analysis=False,
            generate_embeddings=True,
        )
        call_count_after_first = mock_get_text_embeddings.call_count

        # Second registration with identical input should be a cache-hit.
        main.register_standard(
            standard_entries=[std],
            collection=self.collection,
            calculate_gap_analysis=False,
            generate_embeddings=True,
        )
        self.assertEqual(mock_get_text_embeddings.call_count, call_count_after_first)
