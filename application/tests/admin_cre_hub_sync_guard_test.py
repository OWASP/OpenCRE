import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        env = mock.patch.dict(
            os.environ, {"CRE_HUB_SQLITE": str(self.hub)}, clear=False
        )
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ADMIN_REPLACE_CRE_HUB_EMBEDDINGS", None)

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


if __name__ == "__main__":
    unittest.main()
