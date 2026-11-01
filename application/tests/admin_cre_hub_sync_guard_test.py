import sqlite3
import tempfile
import unittest
from pathlib import Path

import sqlalchemy.exc

from application.tests.env_override import set_environ_for_test
from application.utils.admin_panel import service


def _make_embeddings_db(path: Path, doc_types: list) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE embeddings (id INTEGER PRIMARY KEY, doc_type TEXT)")
    conn.executemany(
        "INSERT INTO embeddings (doc_type) VALUES (?)", [(d,) for d in doc_types]
    )
    conn.commit()
    conn.close()


class CreHubSyncGuardTest(unittest.TestCase):
    """The hub sync DELETEs doc_type='CRE' rows; it must not run over existing ones."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hub = Path(self.tmp.name) / "hub.sqlite"
        _make_embeddings_db(self.hub, ["CRE"])
        set_environ_for_test(
            self,
            {"CRE_HUB_SQLITE": str(self.hub)},
            unset=["ADMIN_REPLACE_CRE_HUB_EMBEDDINGS"],
        )

    def test_keeps_existing_cre_embeddings_by_default(self) -> None:
        dest = Path(self.tmp.name) / "dest.sqlite"
        _make_embeddings_db(dest, ["CRE", "CRE", "Standard"])
        out = service.sync_cre_hub_embeddings(f"sqlite:///{dest}")
        self.assertEqual(out["status"], "ok")
        self.assertIn("kept 2 existing CRE embedding rows", out["detail"])
        conn = sqlite3.connect(dest)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0], 3
        )
        conn.close()

    def test_count_is_zero_without_cre_rows_or_table(self) -> None:
        empty = Path(self.tmp.name) / "empty.sqlite"
        _make_embeddings_db(empty, ["Standard"])
        self.assertEqual(service._count_cre_embeddings(f"sqlite:///{empty}"), 0)
        missing = Path(self.tmp.name) / "missing.sqlite"
        self.assertEqual(service._count_cre_embeddings(f"sqlite:///{missing}"), 0)

    def test_count_raises_when_database_cannot_be_opened(self) -> None:
        unopenable = Path(self.tmp.name) / "no_such_dir" / "dest.sqlite"
        with self.assertRaises(sqlalchemy.exc.OperationalError):
            service._count_cre_embeddings(f"sqlite:///{unopenable}")

    def test_sync_refuses_to_run_when_destination_cannot_be_opened(self) -> None:
        unopenable = Path(self.tmp.name) / "no_such_dir" / "dest.sqlite"
        # The guard error propagates before the destructive subprocess is built.
        with self.assertRaises(sqlalchemy.exc.OperationalError):
            service.sync_cre_hub_embeddings(f"sqlite:///{unopenable}")

    def test_count_is_zero_when_embeddings_table_missing(self) -> None:
        other = Path(self.tmp.name) / "other.sqlite"
        conn = sqlite3.connect(other)
        conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        self.assertEqual(service._count_cre_embeddings(f"sqlite:///{other}"), 0)

    def test_count_without_embedding_vec_column_counts_cre_rows(self) -> None:
        dest = Path(self.tmp.name) / "novec.sqlite"
        _make_embeddings_db(dest, ["CRE", "CRE", "Standard"])
        self.assertEqual(service._count_cre_embeddings(f"sqlite:///{dest}"), 2)

    def test_count_with_embedding_vec_column_counts_only_non_null_vectors(
        self,
    ) -> None:
        dest = Path(self.tmp.name) / "vec.sqlite"
        conn = sqlite3.connect(dest)
        conn.execute(
            "CREATE TABLE embeddings "
            "(id INTEGER PRIMARY KEY, doc_type TEXT, embedding_vec BLOB)"
        )
        conn.executemany(
            "INSERT INTO embeddings (doc_type, embedding_vec) VALUES (?, ?)",
            [
                ("CRE", b"\x01"),
                ("CRE", None),
                ("Standard", b"\x02"),
                ("CRE", b"\x03"),
            ],
        )
        conn.commit()
        conn.close()
        self.assertEqual(service._count_cre_embeddings(f"sqlite:///{dest}"), 2)


if __name__ == "__main__":
    unittest.main()
