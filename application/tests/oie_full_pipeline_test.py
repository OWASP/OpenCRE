"""Unit tests for full-pipeline gold key guessing (no DB)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "oie_owasp_eval" / "run_full_pipeline.py"


def _load_fp():
    spec = importlib.util.spec_from_file_location("run_full_pipeline", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_full_pipeline"] = mod
    spec.loader.exec_module(mod)
    return mod


_fp = _load_fp()


class FullPipelineKeyGuessTest(unittest.TestCase):
    def test_asvs_section_from_path_and_text(self) -> None:
        keys = _fp._guess_keys_for_decision(
            path="5.0/en/0x10-V1-Encoding-and-Sanitization.md",
            text="### V1.1.2\nVerify that...",
            repo="OWASP/ASVS",
        )
        self.assertIn("asvs::V1.1.2", keys)

    def test_aisvs_from_filename(self) -> None:
        keys = _fp._guess_keys_for_decision(
            path="1.0/en/0x10-C01-Training-Data-Integrity-and-Traceability.md",
            text="",
            repo="OWASP/AISVS",
        )
        self.assertIn("aisvs::AISVS1", keys)

    def test_cheatsheet_stem(self) -> None:
        keys = _fp._guess_keys_for_decision(
            path="cheatsheets/Authorization_Cheat_Sheet.md",
            text="",
            repo="OWASP/CheatSheetSeries",
        )
        self.assertIn("cheatsheets::Authorization_Cheat_Sheet", keys)

    def test_cheatsheet_section_id_from_hyperlink(self) -> None:
        sid = _fp._cheatsheet_section_id(
            {
                "section": "Authorization Cheat Sheet",
                "hyperlink": (
                    "https://cheatsheetseries.owasp.org/cheatsheets/"
                    "Authorization_Cheat_Sheet.html"
                ),
                "cre_ids": ["128-128"],
            }
        )
        self.assertEqual(sid, "Authorization_Cheat_Sheet")


if __name__ == "__main__":
    unittest.main()
