import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "scripts" / "oie_owasp_eval"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"oie_eval_{name}", EVAL_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MatchGoldTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load("score_b1_opencre_api")
        self.gold = {
            "authentication cheat sheet": {"cre-authn"},
            "multifactor authentication cheat sheet": {"cre-mfa"},
        }

    def test_fuzzy_match_bleeds_into_longer_sheet_name(self) -> None:
        got = self.mod.match_gold({"authentication cheat sheet"}, self.gold)
        self.assertEqual(got, {"cre-authn", "cre-mfa"})

    def test_exact_match_keeps_sheets_separate(self) -> None:
        got = self.mod.match_gold({"authentication cheat sheet"}, self.gold, exact=True)
        self.assertEqual(got, {"cre-authn"})


class ClaimComboTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load("run_exhaustive_switch_grid")
        self.tmp = tempfile.TemporaryDirectory()
        grid = Path(self.tmp.name)
        patcher_grid = patch.object(self.mod, "GRID_DIR", grid)
        patcher_locks = patch.object(self.mod, "LOCKS_DIR", grid / ".locks")
        patcher_grid.start()
        patcher_locks.start()
        self.addCleanup(patcher_grid.stop)
        self.addCleanup(patcher_locks.stop)
        self.addCleanup(self.tmp.cleanup)
        self.grid = grid

    def _write_ok(self, combo_id: str) -> None:
        (self.grid / f"{combo_id}.json").write_text(
            json.dumps({"status": "ok", "headline": {"hits": 1}})
        )

    def test_completed_combo_is_skipped_unless_forced(self) -> None:
        self._write_ok("c1")
        self.assertFalse(self.mod.claim_combo("c1"))
        self.assertTrue(self.mod.claim_combo("c1", force=True))

    def test_live_claim_blocks_second_worker(self) -> None:
        self.assertTrue(self.mod.claim_combo("c2"))
        self.assertFalse(self.mod.claim_combo("c2"))
        self.assertFalse(self.mod.claim_combo("c2", force=True))

    def test_claim_left_by_dead_worker_is_reclaimed(self) -> None:
        lock = self.grid / ".locks" / "c3"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("999999999\n")
        self.assertTrue(self.mod.claim_combo("c3"))
        self.assertEqual((lock / "pid").read_text().strip(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
