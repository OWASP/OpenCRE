import csv
import io
import unittest
from unittest import mock

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

    def test_hydrates_missing_id_from_db_by_name(self) -> None:
        rows = [
            {
                "CRE hierarchy 1": "Known CRE",
                "CRE ID": "",
                "CRE Tags": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "Known CRE"}, {"known cre": "123-456"}),
        ):
            result = master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
        cre = result.results[defs.Credoctypes.CRE.value][0]
        self.assertEqual(cre.name, "Known CRE")
        self.assertEqual(cre.id, "123-456")

    def test_hydrates_id_only_row_name_from_db(self) -> None:
        rows = [
            {
                "CRE hierarchy 1": "123-456",
                "CRE ID": "",
                "CRE Tags": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "Hydrated Name"}, {"hydrated name": "123-456"}),
        ):
            result = master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
        cre = result.results[defs.Credoctypes.CRE.value][0]
        self.assertEqual(cre.name, "Hydrated Name")
        self.assertEqual(cre.id, "123-456")

    def test_raises_on_same_id_different_name_conflict(self) -> None:
        rows = [
            {
                "CRE hierarchy 1": "Sheet Name",
                "CRE ID": "123-456",
                "CRE Tags": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "DB Name"}, {"db name": "123-456"}),
        ):
            with self.assertRaises(ValueError):
                master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)

    def test_accepts_clean_sheet_name_when_db_has_legacy_id_suffix(self) -> None:
        """Sheet omits redundant ' (CRE-ID)' suffix that older DB rows may still have."""
        rows = [
            {
                "CRE hierarchy 1": "Model action privilege minimization",
                "CRE ID": "220-442",
                "CRE Tags": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps",
            return_value=(
                {"220-442": "Model action privilege minimization (220-442)"},
                {"model action privilege minimization (220-442)": "220-442"},
            ),
        ):
            result = master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
        cre = result.results[defs.Credoctypes.CRE.value][0]
        self.assertEqual(cre.id, "220-442")
        self.assertEqual(cre.name, "Model action privilege minimization")

    def test_raises_on_same_name_different_id_conflict(self) -> None:
        rows = [
            {
                "CRE hierarchy 1": "Same Name",
                "CRE ID": "111-111",
                "CRE Tags": "",
            }
        ]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.master_spreadsheet_parser._load_existing_cre_identity_maps",
            return_value=({"222-222": "Same Name"}, {"same name": "222-222"}),
        ):
            with self.assertRaises(ValueError):
                master_spreadsheet_parser.parse_cre_hierarchy_from_rows(rows)
