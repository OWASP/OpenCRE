import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from application.utils import gap_analysis


class _FakeDB:
    def __init__(self, *, backend_url: str = "sqlite:///tmp.db") -> None:
        self.neo_db = object()
        self._cache = {}
        self.session = SimpleNamespace(bind=SimpleNamespace(url=backend_url))

    def gap_analysis_exists(self, cache_key: str) -> bool:
        raw = self._cache.get(cache_key)
        if raw is None:
            return False
        if "->" in cache_key:
            return True
        if isinstance(raw, str):
            return gap_analysis.primary_gap_analysis_payload_is_material(raw)
        return gap_analysis.primary_gap_analysis_payload_is_material(json.dumps(raw))

    def get_gap_analysis_result(self, cache_key: str):
        return self._cache.get(cache_key)


class TestGapAnalysisPairJob(unittest.TestCase):
    def test_primary_gap_analysis_payload_is_material(self):
        g = gap_analysis
        self.assertFalse(g.primary_gap_analysis_payload_is_material(None))
        self.assertFalse(g.primary_gap_analysis_payload_is_material(""))
        self.assertFalse(g.primary_gap_analysis_payload_is_material("{}"))
        self.assertFalse(g.primary_gap_analysis_payload_is_material('{"result":{}}'))
        self.assertFalse(g.primary_gap_analysis_payload_is_material('{"result":[]}'))
        self.assertTrue(
            g.primary_gap_analysis_payload_is_material('{"result":{"x":1}}')
        )
        self.assertTrue(g.primary_gap_analysis_payload_is_material('{"result":[1]}'))

    @patch("application.utils.gap_analysis.redis.connect")
    def test_run_gap_pair_returns_cached_result_without_redis(self, mock_connect):
        db = _FakeDB()
        key = gap_analysis.make_resources_key(["A", "B"])
        db._cache[key] = '{"result":[{"x":1}]}'

        res = gap_analysis.run_gap_pair("A", "B", db)

        self.assertEqual(res, {"result": [{"x": 1}]})
        mock_connect.assert_not_called()

    @patch("application.database.db.gap_analysis")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_run_gap_pair_computes_when_lock_acquired(self, mock_connect, mock_gap):
        db = _FakeDB()
        key = gap_analysis.make_resources_key(["A", "B"])

        class Conn:
            def setnx(self, *_args):
                return True

            def expire(self, *_args):
                return True

            def delete(self, *_args):
                return True

        mock_connect.return_value = Conn()

        def _compute_side_effect(*_args, **kwargs):
            db._cache[key] = '{"result":[{"pair":"A->B"}]}'

        mock_gap.side_effect = _compute_side_effect

        res = gap_analysis.run_gap_pair("A", "B", db)
        self.assertEqual(res, {"result": [{"pair": "A->B"}]})
        mock_gap.assert_called_once()

    @patch("application.database.db.gap_analysis")
    @patch("application.utils.gap_analysis.time.sleep")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_run_gap_pair_waits_then_reads_cache(
        self, mock_connect, mock_sleep, mock_gap
    ):
        db = _FakeDB()
        key = gap_analysis.make_resources_key(["A", "B"])

        class Conn:
            _calls = 0

            def setnx(self, *_args):
                self._calls += 1
                return False

            def expire(self, *_args):
                return True

            def delete(self, *_args):
                return True

        mock_connect.return_value = Conn()

        call_counter = {"n": 0}

        def _exists(cache_key: str) -> bool:
            call_counter["n"] += 1
            if call_counter["n"] >= 3:
                db._cache[cache_key] = '{"result":[{"cached":1}]}'
                return True
            return False

        db.gap_analysis_exists = _exists  # type: ignore[assignment]

        res = gap_analysis.run_gap_pair("A", "B", db, sleep_seconds=0)
        self.assertEqual(res, {"result": [{"cached": 1}]})
        mock_gap.assert_not_called()
        mock_sleep.assert_called()

    def test_run_gap_pair_require_postgres_rejects_sqlite(self):
        db = _FakeDB(backend_url="sqlite:///tmp.db")
        with self.assertRaises(RuntimeError):
            gap_analysis.run_gap_pair("A", "B", db, require_postgres=True)

    @patch("application.database.db.gap_analysis")
    @patch("application.utils.gap_analysis.time.sleep")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_run_gap_pair_retries_transient_compute_error(
        self, mock_connect, mock_sleep, mock_gap
    ):
        db = _FakeDB(backend_url="postgresql://u:p@localhost:5432/db")
        key = gap_analysis.make_resources_key(["A", "B"])

        class Conn:
            def setnx(self, *_args):
                return True

            def expire(self, *_args):
                return True

            def delete(self, *_args):
                return True

        mock_connect.return_value = Conn()
        calls = {"n": 0}

        def _side_effect(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("neo4j service unavailable")
            db._cache[key] = '{"result":[{"ok":1}]}'

        mock_gap.side_effect = _side_effect
        res = gap_analysis.run_gap_pair("A", "B", db, max_compute_retries=2)
        self.assertEqual(res, {"result": [{"ok": 1}]})
        self.assertGreaterEqual(mock_gap.call_count, 2)
        mock_sleep.assert_called()

    @patch("application.database.db.gap_analysis")
    @patch("application.utils.gap_analysis.time.sleep")
    @patch("application.utils.gap_analysis.redis.connect")
    def test_run_gap_pair_recovers_after_stale_lock_and_computes_once(
        self, mock_connect, mock_sleep, mock_gap
    ):
        db = _FakeDB(backend_url="postgresql://u:p@localhost:5432/db")
        key = gap_analysis.make_resources_key(["A", "B"])

        class Conn:
            def __init__(self):
                self._setnx_calls = 0

            def setnx(self, *_args):
                # Simulate interrupted worker: lock exists for a while, then expires.
                self._setnx_calls += 1
                return self._setnx_calls >= 3

            def expire(self, *_args):
                return True

            def delete(self, *_args):
                return True

        mock_connect.return_value = Conn()

        def _compute_side_effect(*_args, **_kwargs):
            db._cache[key] = '{"result":[{"recovered":1}]}'

        mock_gap.side_effect = _compute_side_effect

        res = gap_analysis.run_gap_pair("A", "B", db, sleep_seconds=0)
        self.assertEqual(res, {"result": [{"recovered": 1}]})
        # Ensure stale-lock recovery computes once and does not duplicate writes.
        mock_gap.assert_called_once()
        self.assertGreaterEqual(mock_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
