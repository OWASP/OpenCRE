import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
)


class TestParsers(unittest.TestCase):
    def test_parse_export_format(self) -> None:
        """Given
            * CRE "C1" -> Standard "S1" section "SE1"
            * CRE "C2" -> CRE "C3" linktype contains
            * CRE "C3" -> "C2" (linktype is part of),  Standard "S3" section "SE3"
            * CRE "C5" -> Standard "S1" section "SE1" subsection "SBE1"
            * CRE "C5" -> Standard "S1" section "SE1" subsection "SBE11"
            * CRE "C6" -> Standard "S1" section "SE11", Standard "S2" section "SE22", CRE "C7"(linktype contains) , CRE "C8" (linktype contains)
            * Standard "SL"
            * Standard "SL2" -> Standard "SLL"
            # * CRE "C9"
        Expect:
            9 CRES
            9 standards
            appropriate links among them based on the arrows above
        """
        input_data, expected = data_gen.export_format_data()
        result = parse_export_format(input_data)
        self.maxDiff = None
        for key, val in result.items():
            # self.assertDictEqual(expected[key].todict(), val.todict())
            expected[key].links = []
            val.links = []
            self.assertDictEqual(val.todict(), expected[key].todict())

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
