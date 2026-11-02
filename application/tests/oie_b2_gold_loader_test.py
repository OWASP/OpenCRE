import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from application.utils import mapping_fixtures

ROOT = Path(__file__).resolve().parents[2]


def _load_run_b2():
    path = ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"
    spec = importlib.util.spec_from_file_location("oie_run_b2_pr_mappings", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOieB2GoldLoader(unittest.TestCase):
    def test_shared_harnesses_load_from_mapping_fixtures(self) -> None:
        mod = _load_run_b2()
        shared = 0
        for harness in mod.HARNESSES:
            gold = mod.load_gold(harness)
            self.assertIsInstance(gold, list)
            self.assertGreater(len(gold), 0)
            if harness.get("local_gold"):
                continue
            shared += 1
            self.assertEqual(
                gold,
                mapping_fixtures.load_owasp_mapping_fixture(harness["fixture_name"]),
            )
        self.assertGreaterEqual(shared, 6)

    def test_gold_evidence_preserves_related_expansion_provenance(self) -> None:
        mod = _load_run_b2()
        entries = mapping_fixtures.load_owasp_mapping_fixture("owasp_top10_2025")
        a04 = next(entry for entry in entries if entry["section_id"] == "A04")

        evidence = mod.gold_evidence(a04)

        self.assertEqual(["170-772", "227-045"], evidence["gold_original"])
        self.assertIn("333-858", evidence["gold"])
        self.assertEqual("related_expand_orphan", evidence["gold_remap"])
        self.assertTrue(evidence["gold_is_expanded"])

    def test_gold_evidence_keeps_unremapped_rows_auditable(self) -> None:
        mod = _load_run_b2()
        entries = mapping_fixtures.load_owasp_mapping_fixture("owasp_top10_2025")
        a01 = next(entry for entry in entries if entry["section_id"] == "A01")

        evidence = mod.gold_evidence(a01)

        self.assertEqual(evidence["gold"], evidence["gold_original"])
        self.assertIsNone(evidence["gold_remap"])
        self.assertFalse(evidence["gold_is_expanded"])

    def test_score_run_reports_gold_provenance_for_aligned_and_unaligned_rows(
        self,
    ) -> None:
        mod = _load_run_b2()  # type: ignore[no-untyped-call]
        expanded_harness = {
            "label": "Expanded fixture",
            "pr": 1,
            "fixture_name": "expanded",
        }
        direct_harness = {
            "label": "Direct fixture",
            "pr": 2,
            "fixture_name": "direct",
        }
        expanded_row = {
            "section_id": "E1",
            "cre_ids": ["001-001", "002-002"],
            "cre_ids_original": ["001-001"],
            "gold_remap": "related_expand_orphan",
        }
        expanded_unaligned_row = {
            "section_id": "E2",
            "cre_ids": ["004-004", "005-005"],
            "cre_ids_original": ["004-004"],
            "gold_remap": "related_expand_orphan",
        }
        direct_row = {"section_id": "D1", "cre_ids": ["003-003"]}
        decision = SimpleNamespace(
            chunk_id="chunk-expanded",
            envelope={
                "knowledge": {"locator": {"path": "b2/expanded/E1.txt"}},
                "retrieval": {"reranked": [{"cre_id": "uuid-expanded"}]},
            },
        )
        cre_query = MagicMock()
        cre_query.all.return_value = [
            SimpleNamespace(id="uuid-expanded", external_id="002-002")
        ]
        decision_query = MagicMock()
        decision_query.filter_by.return_value.all.return_value = [decision]

        with patch("application.cmd.cre_main.db_connect"), patch(
            "application.sqla"
        ) as sqla, patch.object(
            mod, "HARNESSES", [expanded_harness, direct_harness]
        ), patch.object(
            mod,
            "load_gold",
            side_effect=[[expanded_row, expanded_unaligned_row], [direct_row]],
        ):
            sqla.session.query.side_effect = [cre_query, decision_query]
            report = mod.score_run("run-1", "sqlite://")

        details = {row["section_id"]: row for row in report["details"]}
        self.assertEqual(
            {
                "gold": ["001-001", "002-002"],
                "gold_original": ["001-001"],
                "gold_remap": "related_expand_orphan",
                "gold_is_expanded": True,
            },
            {
                key: details["E1"][key]
                for key in (
                    "gold",
                    "gold_original",
                    "gold_remap",
                    "gold_is_expanded",
                )
            },
        )
        self.assertTrue(details["E1"]["aligned"])
        self.assertTrue(details["E1"]["hit"])
        self.assertEqual(["002-002"], details["E1"]["predicted"])
        self.assertEqual(
            {
                "gold": ["004-004", "005-005"],
                "gold_original": ["004-004"],
                "gold_remap": "related_expand_orphan",
                "gold_is_expanded": True,
            },
            {
                key: details["E2"][key]
                for key in (
                    "gold",
                    "gold_original",
                    "gold_remap",
                    "gold_is_expanded",
                )
            },
        )
        self.assertFalse(details["E2"]["aligned"])
        self.assertFalse(details["E2"]["hit"])
        self.assertEqual([], details["E2"]["predicted"])
        self.assertEqual(
            {
                "gold": ["003-003"],
                "gold_original": ["003-003"],
                "gold_remap": None,
                "gold_is_expanded": False,
            },
            {
                key: details["D1"][key]
                for key in (
                    "gold",
                    "gold_original",
                    "gold_remap",
                    "gold_is_expanded",
                )
            },
        )
        self.assertFalse(details["D1"]["aligned"])
        self.assertFalse(details["D1"]["hit"])
        self.assertEqual([], details["D1"]["predicted"])
        self.assertEqual(
            {"expanded_rows": 2, "by_remap": {"related_expand_orphan": 2}},
            report["gold_remap_summary"],
        )


class TestOieB2HarvesterLanggraphKwargs(unittest.TestCase):
    def test_inner_harvester_accepts_repos_yaml(self) -> None:
        """LangGraph always passes repos_yaml; B2 must not TypeError (mac arms)."""
        mod = _load_run_b2()
        captured = {}

        class _FakeResult:
            def to_json(self) -> str:
                return '{"ok": true}'

        def fake_pipeline(**kwargs):
            captured["fn"] = kwargs["run_harvester_fn"]
            return _FakeResult()

        hi = MagicMock(__tablename__="harvest_input")
        kq = MagicMock(__tablename__="knowledge_queue")
        dq = MagicMock(__tablename__="decision_queue")
        with patch(
            "application.utils.oie_orchestrator.run_oie_pipeline", fake_pipeline
        ), patch("application.cmd.cre_main.db_connect"), patch(
            "application.database.db.HarvestInput", hi
        ), patch(
            "application.database.db.KnowledgeQueueItem", kq
        ), patch(
            "application.database.db.DecisionQueueItem", dq
        ), patch(
            "application.sqla"
        ) as sqla:
            sqla.session.query.return_value.delete.return_value = 0
            mod.run_pipeline("rid-test", "sqlite://", keep_all_knowledge=False)

        fn = captured["fn"]
        # Same kwargs langgraph_pipeline._run_a forwards — must not TypeError.
        summary = fn(
            MagicMock(),
            "rid-test",
            dry_run=True,
            sync_repos=False,
            repos_yaml="/tmp/repos.yaml",
            max_repos=3,
        )
        self.assertEqual(summary.run_id, "rid-test")


class TestOieB2SourceIdentityPrefix(unittest.TestCase):
    def test_k8s_years_emit_standard_and_version(self) -> None:
        mod = _load_run_b2()
        h22 = next(
            h
            for h in mod.HARNESSES
            if h.get("fixture_name") == "owasp_kubernetes_top10_2022"
        )
        h25 = next(
            h
            for h in mod.HARNESSES
            if h.get("fixture_name") == "owasp_kubernetes_top10_2025"
        )
        self.assertEqual(mod.harness_year(h22), 2022)
        self.assertEqual(mod.harness_year(h25), 2025)
        row = {"section_id": "K06", "section": "Broken Authentication Mechanisms"}
        prefix = mod.source_identity_prefix(row, h22)
        self.assertIn("Standard: OWASP Kubernetes Top 10 2022", prefix)
        self.assertIn("Version: 2022", prefix)
        self.assertIn("Section-ID: K06", prefix)
        # Version before narrative so year_from_text does not pick body years.
        self.assertLess(prefix.index("Version:"), prefix.index("Section-ID:"))

    def test_strip_and_rewrite_keeps_body(self) -> None:
        mod = _load_run_b2()
        harness = {
            "label": "OWASP Kubernetes Top 10 2025",
            "fixture_name": "owasp_kubernetes_top10_2025",
        }
        row = {"section_id": "K01", "section": "Insecure Workload Configurations"}
        old = "Source: K01\nSection: Insecure Workload Configurations\nSection-ID: K01\n\nBODY\n"
        body = mod.strip_source_identity_prefix(old)
        self.assertEqual(body.strip(), "BODY")
        rewritten = mod.source_identity_prefix(row, harness) + body
        self.assertTrue(rewritten.startswith("Standard:"))
        self.assertIn("Version: 2025", rewritten)
        self.assertIn("BODY", rewritten)
