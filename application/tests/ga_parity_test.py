"""Regression tests for GA Postgres vs Neo materiality helpers."""

import unittest

from application.utils import gap_analysis
from application.utils.ga_parity import (
    directed_eligible_pairs,
    pg_neo_material_agree,
)


class TestGaParityHelpers(unittest.TestCase):
    def test_directed_eligible_pairs(self):
        self.assertEqual(
            directed_eligible_pairs(["B", "A"]),
            [("A", "B"), ("B", "A")],
        )
        self.assertEqual(directed_eligible_pairs(["X"]), [])

    def test_pg_neo_material_agree(self):
        self.assertTrue(pg_neo_material_agree(True, 3))
        self.assertTrue(pg_neo_material_agree(False, 0))
        self.assertFalse(pg_neo_material_agree(True, 0))
        self.assertFalse(pg_neo_material_agree(False, 1))


class TestGapAnalysisNoEmptyPrimaryRegression(unittest.TestCase):
    """Empty primary SQL payloads must not count as cached GA (see gap_analysis_exists)."""

    def test_empty_result_json_not_material(self):
        self.assertFalse(
            gap_analysis.primary_gap_analysis_payload_is_material('{"result":{}}')
        )

    def test_whitespace_only_tags_not_material(self):
        self.assertFalse(gap_analysis.primary_gap_analysis_payload_is_material("  "))


if __name__ == "__main__":
    unittest.main()
