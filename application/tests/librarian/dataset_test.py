"""Sanity tests for the populated golden dataset.

These tests run in CI against the committed JSON. They do NOT require the DB —
the DB-driven derivation is covered by ``scripts/build_golden_dataset.py``'s
own ``--check`` mode, which the determinism test invokes when the DB is present.
"""

import json
import os
import subprocess
import sys
import unittest
from collections import Counter

import jsonschema
from pydantic import ValidationError

from application.utils.librarian.schemas import GoldenDatasetRow

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_DATASET = os.path.join(_HERE, "fixtures", "golden_dataset.json")
_JSON_SCHEMA = os.path.join(_HERE, "fixtures", "golden_dataset.schema.json")
_BUILD_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "build_golden_dataset.py")
_DB = os.path.join(_REPO_ROOT, "standards_cache.sqlite")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestGoldenDatasetShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _load(_DATASET)
        cls.json_schema = _load(_JSON_SCHEMA)

    def test_has_at_least_the_asvs_core(self):
        # Master guide §9.3 + golden-dataset-plan §3: at least 277 ASVS-core rows.
        positive_asvs = [
            r
            for r in self.rows
            if r["slice"] == "positive"
            and r["provenance"]["ground_truth_source"].startswith(
                "OpenCRE DB mapping (cre_node_links)"
            )
        ]
        self.assertGreaterEqual(len(positive_asvs), 277)

    def test_all_five_slices_present(self):
        slices = Counter(r["slice"] for r in self.rows)
        self.assertEqual(
            set(slices),
            {"explicit", "positive", "hard_negative", "update", "ambiguous"},
        )
        # Every slice has at least a few rows so the harness can stratify.
        for s, n in slices.items():
            self.assertGreaterEqual(n, 5, msg=f"slice {s} only has {n} rows")

    def test_multilink_positive_rows_exist(self):
        # The Q-D scoring rule has nothing to exercise unless multi-link
        # ground truth is actually present somewhere.
        multi = [
            r
            for r in self.rows
            if r["slice"] == "positive"
            and len(r.get("expected", {}).get("cre_ids") or []) > 1
        ]
        self.assertGreater(len(multi), 0, "no multi-link positive rows present")

    def test_every_row_validates_against_pydantic_model(self):
        errors = []
        for r in self.rows:
            try:
                GoldenDatasetRow.model_validate(r)
            except ValidationError as e:
                errors.append((r.get("id"), str(e)))
        self.assertEqual(errors, [], msg=f"first failure: {errors[:1]}")

    def test_every_row_validates_against_json_schema(self):
        validator = jsonschema.Draft202012Validator(self.json_schema)
        first_errors = []
        for r in self.rows:
            errs = sorted(validator.iter_errors(r), key=str)
            if errs:
                first_errors.append((r.get("id"), [str(e) for e in errs[:1]]))
                if len(first_errors) >= 3:
                    break
        self.assertEqual(first_errors, [])

    def test_provenance_is_recorded_per_row(self):
        for r in self.rows:
            self.assertTrue(
                r["provenance"].get("ground_truth_source"),
                msg=f"row {r.get('id')} missing ground_truth_source",
            )

    def test_ids_are_unique(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))


class TestDatasetDeterminism(unittest.TestCase):
    """The committed JSON must re-derive identically from the DB."""

    def test_build_check_matches_committed_dataset(self):
        if not os.path.exists(_DB):
            self.skipTest("standards_cache.sqlite not present")
        result = subprocess.run(
            [sys.executable, _BUILD_SCRIPT, "--check"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
