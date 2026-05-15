"""Tests for scripts/import_dashboard.py (loaded by file path)."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def _load_import_dashboard():
    path = Path(__file__).resolve().parents[2] / "scripts" / "import_dashboard.py"
    spec = importlib.util.spec_from_file_location("import_dashboard_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_import_dashboard()
create_app = _mod.create_app
terminate_neo4j_transactions = _mod.terminate_neo4j_transactions
neo4j_orphan_gap_transactions = _mod.neo4j_orphan_gap_transactions
ga_coverage_from_standards_and_keys = _mod.ga_coverage_from_standards_and_keys


class GaCoverageMathTest(unittest.TestCase):
    def test_full_matrix_two_standards(self) -> None:
        d = ga_coverage_from_standards_and_keys(["A", "B"], ["A >> B", "B >> A"])
        self.assertEqual(d["directed_pairs_expected"], 2)
        self.assertEqual(d["directed_pairs_missing"], 0)
        self.assertEqual(d["directed_pairs_covered"], 2)

    def test_missing_half(self) -> None:
        d = ga_coverage_from_standards_and_keys(["A", "B"], ["A >> B"])
        self.assertEqual(d["directed_pairs_missing"], 1)
        self.assertEqual(d["stale_pairs_in_storage"], 0)

    def test_three_standards(self) -> None:
        d = ga_coverage_from_standards_and_keys(["X", "Y", "Z"], [])
        self.assertEqual(d["directed_pairs_expected"], 6)

    def test_standard_name_with_hyphen_arrow_still_counts(self) -> None:
        """Primaries may look like ``Foo->Bar >> Baz``; SQL must not treat ``->`` as subresource."""
        d = ga_coverage_from_standards_and_keys(
            ["Foo->Bar", "Baz"], ["Foo->Bar >> Baz", "Baz >> Foo->Bar"]
        )
        self.assertEqual(d["directed_pairs_missing"], 0)
        self.assertEqual(d["directed_pairs_covered"], 2)


class Neo4jOrphanGapTest(unittest.TestCase):
    def test_not_ga_query_never_orphan(self) -> None:
        neo = [{"query": "RETURN 1", "transaction_id": "neo4j-transaction-x"}]
        pending = [
            {
                "state": "started",
                "description": "A->B",
            }
        ]
        self.assertEqual(neo4j_orphan_gap_transactions(neo, pending), [])

    def test_ga_params_match_started_not_orphan(self) -> None:
        neo = [
            {
                "query": "MATCH p = allShortestPaths(...)",
                "transaction_id": "neo4j-transaction-x",
                "parameters": {"name1": "A", "name2": "B"},
            }
        ]
        pending = [{"state": "started", "description": "A->B"}]
        self.assertEqual(neo4j_orphan_gap_transactions(neo, pending), [])

    def test_ga_params_mismatch_started_is_orphan(self) -> None:
        neo = [
            {
                "query": "allShortestPaths",
                "transaction_id": "neo4j-transaction-x",
                "parameters": {"name1": "X", "name2": "Y"},
            }
        ]
        pending = [{"state": "started", "description": "A->B"}]
        o = neo4j_orphan_gap_transactions(neo, pending)
        self.assertEqual(len(o), 1)
        self.assertIn("no matching", o[0].get("orphan_reason", ""))

    def test_ga_no_params_no_started_is_orphan(self) -> None:
        neo = [{"query": "allShortestPaths", "transaction_id": "neo4j-transaction-x"}]
        pending = [{"state": "queued", "description": "A->B"}]
        o = neo4j_orphan_gap_transactions(neo, pending)
        self.assertEqual(len(o), 1)

    def test_ga_no_params_but_started_not_orphan(self) -> None:
        neo = [{"query": "allShortestPaths", "transaction_id": "neo4j-transaction-x"}]
        pending = [{"state": "started", "description": "A->B"}]
        self.assertEqual(neo4j_orphan_gap_transactions(neo, pending), [])


class ImportDashboardTerminateTest(unittest.TestCase):
    def test_terminate_neo4j_rejects_bad_ids(self) -> None:
        out = terminate_neo4j_transactions(["'; DROP--", "not-neo4j-transaction"])
        self.assertFalse(out["ok"])
        self.assertEqual(out.get("error"), "no valid transaction ids")
        self.assertEqual(out.get("terminated"), [])

    def test_api_terminate_403_when_token_wrong(self) -> None:
        app = create_app()
        app.config["TESTING"] = True
        with patch.dict(
            os.environ,
            {
                "CRE_IMPORT_DASHBOARD_ALLOW_TERMINATE": "1",
                "CRE_IMPORT_DASHBOARD_TERMINATE_TOKEN": "secret",
            },
            clear=False,
        ):
            client = app.test_client()
            r = client.post(
                "/api/neo4j/terminate",
                json={"transaction_ids": ["neo4j-transaction-x"]},
                headers={"X-Dashboard-Token": "wrong"},
            )
            self.assertEqual(r.status_code, 403)
            self.assertFalse(r.get_json()["ok"])

    def test_api_terminate_ok_with_token_and_mock_driver(self) -> None:
        app = create_app()
        app.config["TESTING"] = True
        fake_driver = Mock()

        class _Sess:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def run(self, _cypher):
                m = Mock()
                m.consume.return_value = Mock(counters=None)
                return m

        fake_driver.session.return_value = _Sess()

        with patch.dict(
            os.environ,
            {
                "CRE_IMPORT_DASHBOARD_ALLOW_TERMINATE": "1",
                "CRE_IMPORT_DASHBOARD_TERMINATE_TOKEN": "good",
            },
            clear=False,
        ):
            with patch.object(_mod, "_neo4j_driver", return_value=fake_driver):
                client = app.test_client()
                r = client.post(
                    "/api/neo4j/terminate",
                    json={"transaction_ids": ["neo4j-transaction-abc"]},
                    headers={"X-Dashboard-Token": "good"},
                )
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.get_json()["ok"])
                fake_driver.close.assert_called()
