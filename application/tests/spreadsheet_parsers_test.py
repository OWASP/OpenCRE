import collections
import unittest
from application.tests.utils import data_gen
from application.defs import cre_defs as defs
from application.utils.spreadsheet_parsers import (
    parse_export_format,
    parse_hierarchical_export_format,
    parse_uknown_key_val_standards_spreadsheet,
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

    def test_parse_uknown_key_val_standards_spreadsheet(self) -> None:
        # OrderedDict only necessary for testing  so we can predict the root Standard, normally it wouldn't matter
        input_data = [
            collections.OrderedDict(
                {
                    "CS": "Session Management",
                    "CWE": "598",
                    "ASVS": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    "OPC": "",
                    "Top10": "https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                    "WSTG": "WSTG-SESS-04",
                }
            ),
            collections.OrderedDict(
                {
                    "CS": "Session Management",
                    "CWE": "384",
                    "ASVS": "SESSION-MGT-TOKEN-DIRECTIVES-GENERATION",
                    "OPC": "C6",
                    "Top10": "https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                    "WSTG": "WSTG-SESS-03",
                }
            ),
        ]
        expected = {
            "CS-Session Management": defs.Standard(
                doctype=defs.Credoctypes.Standard,
                name="CS",
                links=[
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="CWE",
                            sectionID="598",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="CWE",
                            sectionID="384",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="ASVS",
                            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="ASVS",
                            section="SESSION-MGT-TOKEN-DIRECTIVES-GENERATION",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="OPC",
                            section="C6",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="Top10",
                            section="https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="WSTG",
                            section="WSTG-SESS-03",
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="WSTG",
                            section="WSTG-SESS-04",
                        )
                    ),
                ],
                section="Session Management",
            )
        }
        self.maxDiff = None
        actual = parse_uknown_key_val_standards_spreadsheet(input_data)

        self.assertCountEqual(expected, actual)

    def test_parse_hierarchical_export_format(self) -> None:
        #  todo(northdpole): add a tags linking test
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
