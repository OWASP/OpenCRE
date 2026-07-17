"""Chat/import similarity prefers pgvector when the DB reports it ready."""

import unittest
from unittest.mock import MagicMock, patch

from application.prompt_client import prompt_client as prompt_client_mod


class PgvectorSimilarityCutoverTest(unittest.TestCase):
    def test_node_paginated_uses_pgvector_when_available(self) -> None:
        database = MagicMock()
        database.can_use_pgvector_similarity.return_value = True
        database.find_most_similar_embedding_id.return_value = ("node-1", 0.91)

        handler = prompt_client_mod.PromptHandler.__new__(
            prompt_client_mod.PromptHandler
        )
        handler.database = database

        result = handler.get_id_of_most_similar_node_paginated(
            [0.1, 0.2, 0.3], similarity_threshold=0.7
        )
        self.assertEqual(result, ("node-1", 0.91))
        database.find_most_similar_embedding_id.assert_called_once()
        kwargs = database.find_most_similar_embedding_id.call_args.kwargs
        self.assertEqual(kwargs["id_column"], "node_id")
        database.get_embeddings_by_doc_type_paginated.assert_not_called()

    def test_cre_paginated_uses_pgvector_when_available(self) -> None:
        database = MagicMock()
        database.can_use_pgvector_similarity.return_value = True
        database.find_most_similar_embedding_id.return_value = ("cre-1", 0.88)

        handler = prompt_client_mod.PromptHandler.__new__(
            prompt_client_mod.PromptHandler
        )
        handler.database = database

        result = handler.get_id_of_most_similar_cre_paginated(
            [0.1, 0.2, 0.3], similarity_threshold=0.7
        )
        self.assertEqual(result, ("cre-1", 0.88))
        kwargs = database.find_most_similar_embedding_id.call_args.kwargs
        self.assertEqual(kwargs["id_column"], "cre_id")


class FindMostSimilarEmbeddingIdResilienceTest(unittest.TestCase):
    def test_query_error_returns_no_match(self) -> None:
        from application.database.db import Node_collection

        database = Node_collection.__new__(Node_collection)
        session = MagicMock()
        session.execute.side_effect = RuntimeError("driver boom")
        session.get_bind.return_value = MagicMock()
        database.session = session
        database._pgvector_similarity_ready = True

        with patch("application.database.db.logger"):
            match_id, score = database.find_most_similar_embedding_id(
                [0.1, 0.2, 0.3],
                doc_type="CRE",
                id_column="cre_id",
                similarity_threshold=0.7,
            )
        self.assertIsNone(match_id)
        self.assertIsNone(score)

    def test_sqlite_refuses_pgvector_similarity_with_systemexit(self) -> None:
        from application.database.db import Node_collection
        from application.database.pgvector_utils import PGVECTOR_UNAVAILABLE_EXIT_MSG

        database = Node_collection.__new__(Node_collection)
        database.session = MagicMock()
        database._pgvector_similarity_ready = False

        with self.assertRaises(SystemExit) as cm:
            database.find_most_similar_embedding_id(
                [0.1, 0.2, 0.3],
                doc_type="CRE",
                id_column="cre_id",
                similarity_threshold=0.7,
            )
        self.assertIn("pgvector embeddings are required", str(cm.exception))
        self.assertIn(PGVECTOR_UNAVAILABLE_EXIT_MSG[:40], str(cm.exception))


if __name__ == "__main__":
    unittest.main()
