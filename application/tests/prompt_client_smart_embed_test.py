"""Integration tests for ``CRE_EMBED_SMART_EXTRACT`` in ``generate_embeddings``."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from application.defs import cre_defs
from application.prompt_client import prompt_client

SAMPLE_HTML = """
<html><body><main id="main">
  <div id="ai-program"><h2>AI Program</h2><p>Program governance body text here.</p></div>
  <div id="noise"><p>Other unrelated content unrelated unrelated filler.</p></div>
</main></body></html>
"""


class _AlignClient:
    def align_embedding_span_json(self, _system: str, _user: str) -> dict:
        return {
            "start_bid": "b0",
            "end_bid": "b0",
            "suggested_fragment": "ai-program",
            "confidence": 0.95,
            "should_fallback_full_page": False,
            "rationale": "unit",
        }

    def get_max_batch_size(self):
        return 16

    def get_text_embeddings(self, texts):
        if isinstance(texts, list):
            return [[0.01] * 4 for _ in texts]
        return [0.01] * 4


class _FakeDB:
    def __init__(self):
        self._nodes_by_id = {}
        self.add_embedding = Mock()

    def get_nodes(self, db_id=None):
        n = self._nodes_by_id.get(db_id)
        return [n] if n else []

    def has_node_with_db_id(self, db_id):
        return db_id in self._nodes_by_id

    def get_embedding(self, db_id):
        return []


class TestPromptClientSmartEmbed(unittest.TestCase):
    def setUp(self):
        self._prev_smart = os.environ.get("CRE_EMBED_SMART_EXTRACT")

    def tearDown(self):
        if self._prev_smart is None:
            os.environ.pop("CRE_EMBED_SMART_EXTRACT", None)
        else:
            os.environ["CRE_EMBED_SMART_EXTRACT"] = self._prev_smart

    def test_on_mode_uses_excerpt_and_embeddings_url_with_fragment(self):
        os.environ["CRE_EMBED_SMART_EXTRACT"] = "on"
        fake_db = _FakeDB()
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="AI Program",
            sectionID="aiprogram",
            subsection="",
            hyperlink="https://owaspai.org/go/aiprogram/",
        )
        fake_db._nodes_by_id = {"n1": node}

        emb = prompt_client.in_memory_embeddings.__new__(
            prompt_client.in_memory_embeddings
        )
        emb.ai_client = _AlignClient()
        emb.get_html = Mock(return_value=SAMPLE_HTML)
        emb.get_content = Mock(return_value="fallback full body text")
        emb.clean_content = Mock(side_effect=lambda s: s)
        emb._ensure_smart_embed_caches()

        emb.generate_embeddings(fake_db, ["n1"])
        self.assertEqual(fake_db.add_embedding.call_count, 1)
        kwargs = fake_db.add_embedding.call_args[1]
        self.assertIn("#ai-program", kwargs.get("embeddings_url", ""))
        pos = fake_db.add_embedding.call_args[0]
        embedding_text = pos[3]
        self.assertIn("program governance", embedding_text.lower())
        self.assertIn("__opencre_embed__", embedding_text)

    def test_shadow_mode_full_body_and_hyperlink_url(self):
        os.environ["CRE_EMBED_SMART_EXTRACT"] = "shadow"
        fake_db = _FakeDB()
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="AI Program",
            sectionID="aiprogram",
            subsection="",
            hyperlink="https://owaspai.org/go/aiprogram/",
        )
        fake_db._nodes_by_id = {"n1": node}

        emb = prompt_client.in_memory_embeddings.__new__(
            prompt_client.in_memory_embeddings
        )
        emb.ai_client = _AlignClient()
        emb.get_html = Mock(return_value=SAMPLE_HTML)
        emb.get_content = Mock(return_value="not used when html path works")
        emb.clean_content = Mock(side_effect=lambda s: s)
        emb._ensure_smart_embed_caches()

        emb.generate_embeddings(fake_db, ["n1"])
        kwargs = fake_db.add_embedding.call_args[1]
        self.assertEqual(
            kwargs.get("embeddings_url"), "https://owaspai.org/go/aiprogram/"
        )
        embedding_text = fake_db.add_embedding.call_args[0][3]
        self.assertNotIn("__opencre_embed__", embedding_text)


if __name__ == "__main__":
    unittest.main()
