import json
from pprint import pprint
import tempfile
import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.file import writeToDisk
from application.utils.spreadsheet_parsers import (
    UninitializedMapping,
    get_highest_cre_name,
    get_supported_resources_from_main_csv,
    parse_export_format,
    parse_hierarchical_export_format,
    parse_standards,
    reconcile_uninitializedMappings,
)


class TestParsers(unittest.TestCase):
    def test_parse_export_format(self) -> None:
        input_data, expected = data_gen.export_format_data()
        documents = parse_export_format(input_data)
        actual_cres = documents.pop(defs.Credoctypes.CRE.value)
        standards = documents
        self.maxDiff = None

        expected_cres = expected.pop(defs.Credoctypes.CRE)
        self.assertListEqual(list(actual_cres), list(expected_cres))
        self.assertDictEqual(expected, standards)

    def test_parse_hierarchical_export_format(self) -> None:
        #  TODO(northdpole): add a tags linking test
        input_data, expected_output = data_gen.root_csv_data()
        output = parse_hierarchical_export_format(input_data)
        self.maxDiff = None

        for k, v in expected_output.items():
            for element in v:
                self.assertIn(element, output[k])

        for k, v in output.items():
            for element in v:
                self.assertIn(element, output[k])

    def test_write_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = writeToDisk("sample.txt", tmpdir, "hello")
            self.assertEqual(result, {"sample.txt": "hello"})
            with open(f"{tmpdir}/sample.txt", encoding="utf8") as created:
                self.assertEqual(created.read(), "hello")

    def test_parse_export_format_malformed_cre_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_export_format([{"CRE 0": "bad-format"}])

    def test_parse_standards_with_custom_separator(self) -> None:
        mapping = {
            "sec": "S1|S2",
            "sub": "sub1",
            "lnk": "h1|h2",
            "sid": "id1",
        }
        standards_mapping = {
            "Standards": {
                "CustomStd": {
                    "section": "sec",
                    "sectionID": "sid",
                    "subsection": "sub",
                    "hyperlink": "lnk",
                    "separator": "|",
                }
            }
        }
        links = parse_standards(mapping, standards_mapping)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].document.name, "CustomStd")
        self.assertEqual(links[0].document.section, "S1")
        self.assertEqual(links[0].document.subsection, "sub1")

    def test_parse_standards_without_separator(self) -> None:
        mapping = {"sec": "Section A", "sub": "Sub A", "lnk": "https://x", "sid": "1.1"}
        standards_mapping = {
            "Standards": {
                "BasicStd": {
                    "section": "sec",
                    "sectionID": "sid",
                    "subsection": "sub",
                    "hyperlink": "lnk",
                }
            }
        }
        links = parse_standards(mapping, standards_mapping)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].document.name, "BasicStd")
        self.assertEqual(links[0].document.sectionID, "1.1")

    def test_get_supported_resources_from_main_csv(self) -> None:
        resources = get_supported_resources_from_main_csv()
        self.assertIn("CWE", resources)
        self.assertIn("ASVS", resources)

    def test_get_highest_cre_name(self) -> None:
        hierarchy, name = get_highest_cre_name(
            {
                "CRE hierarchy 1": "Root",
                "CRE hierarchy 2": "Child",
                "CRE hierarchy 3": "",
            },
            highest_hierarchy=3,
        )
        self.assertEqual(hierarchy, 2)
        self.assertEqual(name, "Child")

    def test_reconcile_uninitialized_mappings_success(self) -> None:
        cre_a = defs.CRE(name="A", id="001-001")
        cre_b = defs.CRE(name="B", id="002-002")
        result = reconcile_uninitializedMappings(
            {"A": cre_a, "B": cre_b},
            [
                UninitializedMapping(
                    complete_cre=cre_a,
                    other_cre_name="B",
                    relationship=defs.LinkTypes.Related,
                )
            ],
        )
        self.assertTrue(
            any(
                link.document.name == "B" and link.ltype == defs.LinkTypes.Related
                for link in result["A"].links
            )
        )

    def test_reconcile_uninitialized_mappings_missing_cre_raises(self) -> None:
        cre_a = defs.CRE(name="A", id="001-001")
        with self.assertRaises(ValueError):
            reconcile_uninitializedMappings(
                {"A": cre_a},
                [
                    UninitializedMapping(
                        complete_cre=cre_a,
                        other_cre_name="Missing",
                        relationship=defs.LinkTypes.Related,
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()
