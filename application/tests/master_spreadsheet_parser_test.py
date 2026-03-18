import csv
import io
import unittest

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers import master_spreadsheet_parser


class TestMasterSpreadsheetParser(unittest.TestCase):
    def test_parse_cre_hierarchy_from_rows_happy_path(self) -> None:
        """
        Minimal happy-path: one CRE row with hierarchy.
        Ensures CREs are parsed and tagged, standards are ignored here.
        """
        # Single row in the same shape as hierarchical export header expects
        rows = [
            {
                "CRE 0": "000-001|Root CRE",
                "CRE hierarchy 1": "Root CRE",
                "CRE ID": "000-001",
                "CRE Tags": "tag1,tag2",
            }
        ]

        result = master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
        self.assertTrue(result.calculate_gap_analysis)
        self.assertTrue(result.calculate_embeddings)
        self.assertIn(defs.Credoctypes.CRE.value, result.results)

        cres = result.results[defs.Credoctypes.CRE.value]
        self.assertEqual(len(cres), 1)
        cre = cres[0]
        self.assertEqual(cre.id, "000-001")
        self.assertEqual(cre.name, "Root CRE")
        # Tags should include family/subtype/source/audience/maturity
        self.assertIn("family:standard", cre.tags)
        self.assertIn("subtype:requirements_standard", cre.tags)
        self.assertIn("source:opencre_master_sheet", cre.tags)
        self.assertIn("audience:architect", cre.tags)
        self.assertIn("maturity:stable", cre.tags)

        # No standard collections should be present in this CRE-only parse
        self.assertEqual(list(result.results.keys()), [defs.Credoctypes.CRE.value])

    def test_parse_cre_hierarchy_from_rows_empty(self) -> None:
        rows: list[dict[str, str]] = []
        result = master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
        # No documents, but a well-formed ParseResult
        self.assertIsNotNone(result)
        self.assertFalse(result.results)

