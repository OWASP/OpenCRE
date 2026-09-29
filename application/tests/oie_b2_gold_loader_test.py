import importlib.util
import unittest
from pathlib import Path

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
