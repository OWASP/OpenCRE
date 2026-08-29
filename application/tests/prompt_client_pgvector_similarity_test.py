"""Chat/import similarity prefers pgvector when the DB reports it ready."""

import unittest
from typing import Any, Callable, Dict, List, Tuple
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


def _paginated_side_effect(
    pages: Dict[int, Dict[str, List[float]]],
) -> Callable[..., Tuple[Dict[str, List[float]], int, int]]:
    """Build a ``get_embeddings_by_doc_type_paginated`` side_effect from a
    ``{page_number: {id: embedding}}`` fixture.

    Mirrors the real method's contract (page is 1-indexed, ``total_pages`` is
    the page count, missing/absent ``page`` defaults to 1 like the real
    method's first call in ``get_id_of_most_similar_cre_paginated``).
    """
    total_pages = len(pages)

    def _side_effect(
        *args: Any, **kwargs: Any
    ) -> Tuple[Dict[str, List[float]], int, int]:
        page = kwargs.get("page", 1)
        return pages.get(page, {}), total_pages, page

    return _side_effect


class PaginatedSimilarityFallbackTest(unittest.TestCase):
    """Non-pgvector fallback path of the two ``_paginated`` similarity
    lookups: every page must be visited exactly once, in order, including
    the final one. Regression coverage for the page-alignment bug where the
    fallback silently dropped trailing pages.
    """

    QUERY_EMBEDDING = [1.0, 0.0]
    MATCHING_VECTOR = [1.0, 0.0]  # cosine similarity 1.0 with the query
    NOISE_VECTOR = [0.0, 1.0]  # cosine similarity 0.0 with the query

    def _make_handler(
        self, can_use_pgvector: bool, pages: Dict[int, Dict[str, List[float]]]
    ) -> Tuple[prompt_client_mod.PromptHandler, MagicMock]:
        database = MagicMock()
        database.can_use_pgvector_similarity.return_value = can_use_pgvector
        database.get_embeddings_by_doc_type_paginated.side_effect = (
            _paginated_side_effect(pages)
        )
        handler = prompt_client_mod.PromptHandler.__new__(
            prompt_client_mod.PromptHandler
        )
        handler.database = database
        return handler, database

    def test_node_paginated_finds_match_only_on_final_page(self) -> None:
        # 3 pages; the only match is on the last one. The old implementation
        # never processed it (it processed page 1 twice, page 2 once, and
        # discarded page 3 after fetching it).
        pages = {
            1: {"noise-1": self.NOISE_VECTOR},
            2: {"noise-2": self.NOISE_VECTOR},
            3: {"target-node": self.MATCHING_VECTOR},
        }
        handler, database = self._make_handler(can_use_pgvector=False, pages=pages)

        result = handler.get_id_of_most_similar_node_paginated(
            self.QUERY_EMBEDDING, similarity_threshold=0.5
        )

        self.assertEqual(result, ("target-node", 1.0))
        database.find_most_similar_embedding_id.assert_not_called()

    def test_cre_paginated_finds_match_only_on_final_page(self) -> None:
        # Same fixture shape for the CRE method, whose loop bound excluded
        # the final page outright (range(starting_page, total_pages)).
        pages = {
            1: {"noise-1": self.NOISE_VECTOR},
            2: {"noise-2": self.NOISE_VECTOR},
            3: {"target-cre": self.MATCHING_VECTOR},
        }
        handler, database = self._make_handler(can_use_pgvector=False, pages=pages)

        result = handler.get_id_of_most_similar_cre_paginated(
            self.QUERY_EMBEDDING, similarity_threshold=0.5
        )

        self.assertEqual(result, ("target-cre", 1.0))
        database.find_most_similar_embedding_id.assert_not_called()

    def test_node_paginated_single_page(self) -> None:
        pages = {1: {"only-node": self.MATCHING_VECTOR}}
        handler, database = self._make_handler(can_use_pgvector=False, pages=pages)

        result = handler.get_id_of_most_similar_node_paginated(
            self.QUERY_EMBEDDING, similarity_threshold=0.5
        )

        self.assertEqual(result, ("only-node", 1.0))
        # Single page: no page beyond it should ever be requested.
        self.assertEqual(database.get_embeddings_by_doc_type_paginated.call_count, 1)

    def test_cre_paginated_single_page(self) -> None:
        pages = {1: {"only-cre": self.MATCHING_VECTOR}}
        handler, database = self._make_handler(can_use_pgvector=False, pages=pages)

        result = handler.get_id_of_most_similar_cre_paginated(
            self.QUERY_EMBEDDING, similarity_threshold=0.5
        )

        self.assertEqual(result, ("only-cre", 1.0))
        self.assertEqual(database.get_embeddings_by_doc_type_paginated.call_count, 1)


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
