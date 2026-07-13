import unittest
from unittest import mock

from application.defs import cre_defs as defs
from application.utils.external_project_parsers.parsers import myopencre_parser


class MyOpenCreParserIdentityTest(unittest.TestCase):
    def test_hydrates_missing_id_from_db_by_name(self) -> None:
        cres = [defs.CRE(name="Known CRE", id="111-111")]
        cres[0].id = ""
        with mock.patch(
            "application.utils.external_project_parsers.parsers.myopencre_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "Known CRE"}, {"known cre": "123-456"}),
        ):
            out = myopencre_parser._reconcile_cre_identities(cres)
        self.assertEqual(out[0].name, "Known CRE")
        self.assertEqual(out[0].id, "123-456")

    def test_hydrates_id_only_name_from_db(self) -> None:
        cres = [defs.CRE(name="123-456", id="123-456")]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.myopencre_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "Hydrated Name"}, {"hydrated name": "123-456"}),
        ):
            out = myopencre_parser._reconcile_cre_identities(cres)
        self.assertEqual(out[0].name, "Hydrated Name")
        self.assertEqual(out[0].id, "123-456")

    def test_raises_on_same_id_different_name_conflict(self) -> None:
        cres = [defs.CRE(name="Sheet Name", id="123-456")]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.myopencre_parser._load_existing_cre_identity_maps",
            return_value=({"123-456": "DB Name"}, {"db name": "123-456"}),
        ):
            with self.assertRaises(ValueError):
                myopencre_parser._reconcile_cre_identities(cres)

    def test_raises_on_same_name_different_id_conflict(self) -> None:
        cres = [defs.CRE(name="Same Name", id="111-111")]
        with mock.patch(
            "application.utils.external_project_parsers.parsers.myopencre_parser._load_existing_cre_identity_maps",
            return_value=({"222-222": "Same Name"}, {"same name": "222-222"}),
        ):
            with self.assertRaises(ValueError):
                myopencre_parser._reconcile_cre_identities(cres)


class MyOpenCreCsvValidationTest(unittest.TestCase):
    def test_accepts_well_formed_cre_cells(self) -> None:
        myopencre_parser.validate_cre_csv_rows(
            [{"CRE 0": "123-456|Access Control", "standard|name": "ASVS"}]
        )

    def test_rejects_short_cre_id(self) -> None:
        with self.assertRaises(ValueError) as cm:
            myopencre_parser.validate_cre_csv_rows(
                [{"CRE 0": "12-456|Bad Id", "standard|name": "ASVS"}]
            )
        self.assertIn("Expected XXX-XXX|Name", str(cm.exception))
        self.assertIn("row 2", str(cm.exception))

    def test_rejects_missing_separator(self) -> None:
        with self.assertRaises(ValueError) as cm:
            myopencre_parser.validate_cre_csv_rows(
                [{"CRE 0": "123-456 Access Control", "standard|name": "ASVS"}]
            )
        self.assertIn("Expected XXX-XXX|Name", str(cm.exception))

    def test_skips_empty_cre_cells(self) -> None:
        myopencre_parser.validate_cre_csv_rows(
            [{"CRE 0": "", "CRE 1": "n/a", "standard|name": "ASVS"}]
        )


if __name__ == "__main__":
    unittest.main()
