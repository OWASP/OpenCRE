import importlib.util
import pathlib
import unittest
from unittest import mock

_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "e5f6a7b8c9d0_add_agent_halfvec_hnsw_index.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("agent_hnsw_migration", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentHnswMigrationTest(unittest.TestCase):
    def test_merges_the_two_previous_heads(self) -> None:
        m = _load()
        self.assertEqual(set(m.down_revision), {"c9d0e1f2a3b4", "f5a6b7c8d9e0"})

    def test_noop_off_postgres(self) -> None:
        m = _load()
        bind = mock.Mock()
        bind.dialect.name = "sqlite"
        with mock.patch.object(m.op, "get_bind", return_value=bind), mock.patch.object(
            m.op, "execute"
        ) as execute:
            m.upgrade()
            m.downgrade()
        execute.assert_not_called()

    def test_builds_index_with_the_column_dimension(self) -> None:
        m = _load()
        bind = mock.Mock()
        bind.dialect.name = "postgresql"
        bind.exec_driver_sql.side_effect = [
            mock.Mock(fetchone=lambda: (1,)),  # vector extension present
            mock.Mock(fetchone=lambda: (3072,)),  # column typmod
        ]
        ctx = mock.MagicMock()
        with mock.patch.object(m.op, "get_bind", return_value=bind), mock.patch.object(
            m.op, "get_context", return_value=ctx
        ), mock.patch.object(m.op, "execute") as execute:
            m.upgrade()
        sql = execute.call_args[0][0]
        self.assertIn("halfvec(3072)", sql)
        self.assertIn("CONCURRENTLY", sql)
        self.assertIn("source_channel = 'owasp_agent_meta'", sql)

    def test_skips_columns_wider_than_halfvec_limit(self) -> None:
        m = _load()
        bind = mock.Mock()
        bind.dialect.name = "postgresql"
        bind.exec_driver_sql.side_effect = [
            mock.Mock(fetchone=lambda: (1,)),
            mock.Mock(fetchone=lambda: (8192,)),
        ]
        with mock.patch.object(m.op, "get_bind", return_value=bind), mock.patch.object(
            m.op, "execute"
        ) as execute:
            m.upgrade()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
