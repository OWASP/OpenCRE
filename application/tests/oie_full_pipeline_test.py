"""Unit tests for full-pipeline gold key guessing and CRE pick parity (no DB)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "oie_owasp_eval" / "run_full_pipeline.py"
_B2 = ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"


def _load_fp():
    spec = importlib.util.spec_from_file_location("run_full_pipeline", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_full_pipeline"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_b2():
    spec = importlib.util.spec_from_file_location("run_b2_pr_mappings", _B2)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_b2_pr_mappings"] = mod
    spec.loader.exec_module(mod)
    return mod


_fp = _load_fp()
_b2 = _load_b2()


class FullPipelineKeyGuessTest(unittest.TestCase):
    def test_asvs_section_from_path_and_text(self) -> None:
        keys = _fp._guess_keys_for_decision(
            path="5.0/en/0x10-V1-Encoding-and-Sanitization.md",
            text="### V1.1.2\nVerify that...",
            repo="OWASP/ASVS",
        )
        self.assertIn("asvs::V1.1.2", keys)

    def test_asvs_prefers_explicit_single_section_id(self) -> None:
        """Outer heading soup must not dilute a clean extractor Section-ID."""
        keys = _fp._guess_keys_for_decision(
            path="5.0/en/0x10-V1-Encoding-and-Sanitization.md",
            text=(
                "Standard: ASVS\n"
                "Version: 5.0\n"
                "Source: 0x10-V1-Encoding-and-Sanitization.md\n"
                "Section-ID: V1.1.2\n"
                "Section: V1 Encoding\n\n"
                "Source: V1.1.2\n"
                "Section-ID: V1.1.2\n"
                "Section: Verify that output encoding is applied.\n\n"
                "Verify that output encoding is applied.\n"
            ),
            repo="OWASP/ASVS",
        )
        self.assertEqual(keys, {"asvs::V1.1.2"})

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


class FullPipelineTop2ParityTest(unittest.TestCase):
    def test_top2_matches_b2_rerank_union_vector(self) -> None:
        uuid_to_ext = {
            "u-rerank-1": "111-111",
            "u-rerank-2": "222-222",
            "u-rerank-3": "333-333",
            "u-vec-1": "444-444",
            "u-vec-2": "555-555",
            "u-link": "666-666",
        }
        envelope = {
            "suggested_links": [{"cre_id": "u-link", "confidence": 0.9}],
            "retrieval": {
                "reranked": [
                    {"cre_id": "u-rerank-1", "score_rerank": 1.0},
                    {"cre_id": "u-rerank-2", "score_rerank": 0.9},
                    {"cre_id": "u-rerank-3", "score_rerank": 0.8},
                ],
                "candidates": [
                    {"cre_id": "u-vec-2", "score_vector": 0.5},
                    {"cre_id": "u-vec-1", "score_vector": 0.9},
                    {"cre_id": "u-rerank-1", "score_vector": 0.2},
                ],
            },
        }
        b2 = _b2.top2_cre_external_ids(envelope, uuid_to_ext)
        fp = _fp._top2_cre_ids(envelope, uuid_to_ext)
        self.assertEqual(fp, b2)
        # Must not stop at suggested_links-only (legacy fullpipe bug).
        self.assertIn("111-111", fp)
        self.assertIn("222-222", fp)
        self.assertIn("444-444", fp)
        self.assertNotIn("666-666", fp)


if __name__ == "__main__":
    unittest.main()
