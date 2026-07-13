"""Tests for pgvector embedding helpers (dim gate, literal, backfill SQL)."""

import os
import unittest
from unittest.mock import MagicMock

from application.database.pgvector_utils import (
    MultiDimEmbeddingError,
    backfill_embedding_vec,
    collect_distinct_dims,
    csv_embeddings_to_literal,
    most_similar_id_sql,
    parse_csv_embedding_dim,
    require_single_embedding_dim,
    to_pgvector_literal,
)


class PgvectorLiteralTest(unittest.TestCase):
    def test_to_pgvector_literal(self) -> None:
        self.assertEqual(to_pgvector_literal([1, 2.5, 0]), "[1.0,2.5,0.0]")

    def test_csv_to_literal(self) -> None:
        self.assertEqual(csv_embeddings_to_literal("1.0,2.0"), "[1.0,2.0]")

    def test_parse_csv_dim(self) -> None:
        self.assertEqual(parse_csv_embedding_dim("0.1,0.2,0.3"), 3)
        self.assertEqual(parse_csv_embedding_dim(""), 0)


class DistinctDimsTest(unittest.TestCase):
    def test_single_dim_from_metadata(self) -> None:
        self.assertEqual(collect_distinct_dims([(3, "1,2,3"), (3, "4,5,6")]), {3})

    def test_csv_fallback_when_metadata_missing(self) -> None:
        self.assertEqual(collect_distinct_dims([(None, "1,2"), (None, "3,4")]), {2})

    def test_mixed_dims_detected(self) -> None:
        self.assertEqual(
            collect_distinct_dims([(2, "1,2"), (3, "1,2,3")]),
            {2, 3},
        )


class RequireSingleDimTest(unittest.TestCase):
    def test_raises_on_multiple_dims(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            (2, "1,2"),
            (3, "1,2,3"),
        ]
        with self.assertRaises(MultiDimEmbeddingError) as cm:
            require_single_embedding_dim(conn)
        self.assertIn("multiple embedding dimensions", str(cm.exception))
        self.assertIn("Heroku", str(cm.exception))

    def test_returns_single_dim(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            (768, "1," * 767 + "1"),
            (768, None),
        ]
        self.assertEqual(require_single_embedding_dim(conn), 768)

    def test_empty_table_uses_env_dim(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        os.environ["CRE_EMBED_EXPECTED_DIM"] = "4"
        try:
            self.assertEqual(require_single_embedding_dim(conn), 4)
        finally:
            os.environ.pop("CRE_EMBED_EXPECTED_DIM", None)

    def test_empty_table_without_env_raises(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        os.environ.pop("CRE_EMBED_EXPECTED_DIM", None)
        with self.assertRaises(RuntimeError):
            require_single_embedding_dim(conn)


class BackfillTest(unittest.TestCase):
    def test_backfill_runs_idempotent_update(self) -> None:
        conn = MagicMock()
        result = MagicMock()
        result.rowcount = 2
        conn.execute.return_value = result
        self.assertEqual(backfill_embedding_vec(conn, 3), 2)
        args, kwargs = conn.execute.call_args
        sql = str(args[0])
        self.assertIn("embedding_vec IS NULL", sql)
        self.assertIn("CAST", sql)
        # bound dim
        bound = args[1] if len(args) > 1 else kwargs.get("parameters") or kwargs
        if isinstance(bound, dict):
            self.assertEqual(bound.get("dim"), 3)


class MostSimilarSqlTest(unittest.TestCase):
    def test_sql_uses_id_column_and_cosine(self) -> None:
        sql = most_similar_id_sql("node_id")
        self.assertIn("node_id", sql)
        self.assertIn("<=>", sql)
        self.assertIn("LIMIT 1", sql)

    def test_rejects_unknown_column(self) -> None:
        with self.assertRaises(ValueError):
            most_similar_id_sql("id")


if __name__ == "__main__":
    unittest.main()
