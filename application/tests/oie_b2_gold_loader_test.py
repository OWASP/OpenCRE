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
