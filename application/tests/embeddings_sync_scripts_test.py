"""Unit tests for embeddings sync / SQLite rewrite helpers."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.rewrite_sqlite_embeddings_to_vec import rewrite
from scripts.sync_embeddings_table import _as_vec_literal, _fetch_sqlite_embeddings


class AsVecLiteralTest(unittest.TestCase):
    def test_none_and_empty_return_none(self) -> None:
        self.assertIsNone(_as_vec_literal(None))
        self.assertIsNone(_as_vec_literal(""))
        self.assertIsNone(_as_vec_literal("[]"))
        self.assertIsNone(_as_vec_literal("  [ ]  "))

    def test_literal_and_csv(self) -> None:
        self.assertEqual(_as_vec_literal("[1.0,2.0]"), "[1.0,2.0]")
        self.assertEqual(_as_vec_literal("1.0,2.0"), "[1.0,2.0]")


class SyncSqliteFetchTest(unittest.TestCase):
    def test_skips_empty_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.sqlite"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE embeddings (
                    embedding_vec TEXT,
                    doc_type TEXT,
                    cre_id TEXT,
                    node_id TEXT,
                    embeddings_content TEXT,
                    embeddings_url TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO embeddings VALUES (?,?,?,?,?,?)",
                [
                    ("[0.1,0.2]", "CRE", "a", None, "x", None),
                    (None, "CRE", "b", None, "y", None),
                    ("[]", "CRE", "c", None, "z", None),
                ],
            )
            conn.commit()
            conn.close()
            _cols, rows, skipped = _fetch_sqlite_embeddings(str(path))
            self.assertEqual(len(rows), 1)
            self.assertEqual(skipped, 2)
            self.assertEqual(rows[0][0], "[0.1,0.2]")


class RewriteSqliteTest(unittest.TestCase):
    def test_idempotent_and_no_double_brackets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.sqlite"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE embeddings (
                    id TEXT,
                    doc_type TEXT NOT NULL,
                    cre_id TEXT,
                    node_id TEXT,
                    embeddings TEXT NOT NULL,
                    embeddings_content TEXT,
                    embeddings_url TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?)",
                ("1", "CRE", "a", None, "0.1,0.2", "t", None),
            )
            conn.execute(
                "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?)",
                ("2", "CRE", "b", None, "[0.3,0.4]", "t2", None),
            )
            conn.commit()
            conn.close()

            self.assertEqual(rewrite(str(path)), 0)
            self.assertEqual(rewrite(str(path)), 0)  # already vec-only

            conn = sqlite3.connect(path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)")}
            self.assertIn("embedding_vec", cols)
            self.assertNotIn("embeddings", cols)
            vecs = [
                r[0]
                for r in conn.execute(
                    "SELECT embedding_vec FROM embeddings ORDER BY id"
                )
            ]
            self.assertEqual(vecs[0], "[0.1,0.2]")
            self.assertEqual(vecs[1], "[0.3,0.4]")  # not [[0.3,0.4]]
            conn.close()

    def test_rerun_safe_after_leftover_embeddings_new(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.sqlite"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE embeddings (
                    id TEXT,
                    doc_type TEXT NOT NULL,
                    cre_id TEXT,
                    node_id TEXT,
                    embeddings TEXT NOT NULL,
                    embeddings_content TEXT,
                    embeddings_url TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?)",
                ("1", "CRE", "a", None, "1,2", None, None),
            )
            # Simulate interrupted prior run.
            conn.execute(
                "CREATE TABLE embeddings_new (id TEXT, doc_type TEXT, embedding_vec TEXT)"
            )
            conn.commit()
            conn.close()
            self.assertEqual(rewrite(str(path)), 0)


if __name__ == "__main__":
    unittest.main()
