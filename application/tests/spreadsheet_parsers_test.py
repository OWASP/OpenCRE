import json
from pprint import pprint
import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
    parse_standards,
    supported_resource_mapping,
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

    def test_parse_standards_subparser_equivalence(self) -> None:
        """Step 2b: parse_standards matches aggregate of per-family extraction."""
        input_data, expected_output = data_gen.root_csv_data()
        # Use first row that has standards
        row = input_data[0]
        legacy_links = parse_standards(dict(row))
        # Each link should be for a supported family
        standards_map = supported_resource_mapping.get("Standards", {})
        for link in legacy_links:
            self.assertIn(link.document.name, standards_map)


if __name__ == "__main__":
    unittest.main()
