import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from application.defs import cre_defs
from application.prompt_client import prompt_client


class _FakeDB:
    def __init__(self):
        self._cre_by_id = {}
        self._nodes_by_id = {}
        self._emb_by_id = {}
        self.add_embedding = Mock()

    def get_cre_by_db_id(self, db_id):
        return self._cre_by_id.get(db_id)

    def get_nodes(self, db_id=None):
        if db_id is None:
            return []
        node = self._nodes_by_id.get(db_id)
        return [node] if node else []

    def get_embedding(self, db_id):
        emb = self._emb_by_id.get(db_id)
        return [emb] if emb else []

    def list_cre_ids(self):
        return list(self._cre_by_id.keys())


class TestIncrementalEmbeddings(unittest.TestCase):
    def test_generate_embeddings_skips_unchanged_cre_content(self):
        fake_db = _FakeDB()
        cre1 = cre_defs.CRE(id="111-111", name="CRE-1", description="desc-1")
        cre2 = cre_defs.CRE(id="222-222", name="CRE-2", description="desc-2")
        fake_db._cre_by_id = {"db-1": cre1, "db-2": cre2}

        unchanged_content = (
            f"{cre1.doctype}\n name:{cre1.name}\n description:{cre1.description}\n id:{cre1.id}\n "
        )
        fake_db._emb_by_id["db-1"] = SimpleNamespace(embeddings_content=unchanged_content)

        emb = prompt_client.in_memory_embeddings.__new__(prompt_client.in_memory_embeddings)
        emb.ai_client = Mock()
        emb.ai_client.get_max_batch_size.return_value = 16
        emb.ai_client.get_text_embeddings.return_value = [[0.1, 0.2]]

        emb.generate_embeddings(fake_db, ["db-1", "db-2"])

        self.assertEqual(fake_db.add_embedding.call_count, 1)
        args = fake_db.add_embedding.call_args[0]
        self.assertEqual(args[0].id, "db-2")

    def test_prompt_handler_cre_embeddings_skip_unchanged(self):
        fake_db = _FakeDB()
        cre1 = cre_defs.CRE(id="333-333", name="CRE-3", description="desc-3")
        cre2 = cre_defs.CRE(id="444-444", name="CRE-4", description="desc-4")
        fake_db._cre_by_id = {"db-3": cre1, "db-4": cre2}

        unchanged_content = (
            f"{cre1.doctype}\n name:{cre1.name}\n description:{cre1.description}\n id:{cre1.id}\n "
        )
        fake_db._emb_by_id["db-3"] = SimpleNamespace(embeddings_content=unchanged_content)

        ph = prompt_client.PromptHandler.__new__(prompt_client.PromptHandler)
        ph.database = fake_db
        ph.ai_client = Mock()
        ph.ai_client.get_max_batch_size.return_value = 16
        # Single item batch shape can be single embedding vector.
        ph.ai_client.get_text_embeddings.return_value = [0.11, 0.22]
        ph.embeddings_instance = Mock()

        ph.generate_embeddings_for(cre_defs.Credoctypes.CRE.value)

        self.assertEqual(fake_db.add_embedding.call_count, 1)
        args = fake_db.add_embedding.call_args[0]
        self.assertEqual(args[0].id, "db-4")

    def test_generate_embeddings_recalculates_when_node_content_changes(self):
        fake_db = _FakeDB()
        current_node = cre_defs.Standard(
            name="ISO 27001",
            section="Changed section text",
            sectionID="5.1",
            subsection="",
            hyperlink="",
            version="",
        )
        old_node = cre_defs.Standard(
            name="ISO 27001",
            section="Original section text",
            sectionID="5.1",
            subsection="",
            hyperlink="",
            version="",
        )
        fake_db._nodes_by_id = {"node-1": current_node}
        fake_db._emb_by_id["node-1"] = SimpleNamespace(
            embeddings_content=prompt_client.normalize_embeddings_content(old_node.__repr__())
        )

        emb = prompt_client.in_memory_embeddings.__new__(prompt_client.in_memory_embeddings)
        emb.ai_client = Mock()
        emb.ai_client.get_max_batch_size.return_value = 16
        emb.ai_client.get_text_embeddings.return_value = [[0.9, 0.8]]

        emb.generate_embeddings(fake_db, ["node-1"])

        self.assertEqual(fake_db.add_embedding.call_count, 1)
        args = fake_db.add_embedding.call_args[0]
        self.assertEqual(args[0].id, "node-1")


if __name__ == "__main__":
    unittest.main()
