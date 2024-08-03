import json
from pprint import pprint
import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
)


class TestParsers(unittest.TestCase):

    def test_parse_export_format(self) -> None:

        input_data, expected = data_gen.export_format_data()
        cres, standards = parse_export_format(input_data)
        self.maxDiff = None

        self.assertListEqual(list(cres), list(expected[defs.Credoctypes.CRE]))
        self.assertListEqual(list(expected[defs.Credoctypes.Standard]), list(standards))

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


if __name__ == "__main__":
    unittest.main()
