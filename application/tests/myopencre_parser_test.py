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


if __name__ == "__main__":
    unittest.main()
