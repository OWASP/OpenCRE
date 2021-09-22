import collections
import unittest
from pprint import pprint

from application.defs import cre_defs as defs
from application.utils.parsers import parse_export_format  # type: ignore
from application.utils.parsers import (
    parse_hierarchical_export_format,
    parse_uknown_key_val_spreadsheet,
    parse_v0_standards,
    parse_v1_standards,
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
        input_data = [
            {
                "CRE:description": "C1 description",
                "CRE:id": "1",
                "CRE:name": "C1",
                "S1:hyperlink": "https://example.com/S1",
                "S1:link_type": "Linked To",
                "S1:section": "SE1",
                "S1:subsection": "SBE1",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "",
                "Linked_CRE_0:link_type": "",
                "Linked_CRE_0:name": "",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "C2 description",
                "CRE:id": "2",
                "CRE:name": "C2",
                "S1:hyperlink": "",
                "S1:link_type": "",
                "S1:section": "",
                "S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "3",
                "Linked_CRE_0:link_type": "Contains",
                "Linked_CRE_0:name": "C3",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "C3 description",
                "CRE:id": "3",
                "CRE:name": "C3",
                "S1:hyperlink": "",
                "S1:link_type": "",
                "S1:section": "",
                "S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "https://example.com/S3",
                "S3:link_type": "Linked To",
                "S3:section": "SE3",
                "S3:subsection": "SBE3",
                "Linked_CRE_0:id": "2",
                "Linked_CRE_0:link_type": "Is Part Of",
                "Linked_CRE_0:name": "C2",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "C5 description",
                "CRE:id": "5",
                "CRE:name": "C5",
                "S1:hyperlink": "https://example.com/S1",
                "S1:link_type": "Linked To",
                "S1:section": "SE1",
                "S1:subsection": "SBE1",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "",
                "Linked_CRE_0:link_type": "",
                "Linked_CRE_0:name": "",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "C5 description",
                "CRE:id": "5",
                "CRE:name": "C5",
                "S1:hyperlink": "https://example.com/S1",
                "S1:link_type": "Linked To",
                "S1:section": "SE1",
                "S1:subsection": "SBE11",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "",
                "Linked_CRE_0:link_type": "",
                "Linked_CRE_0:name": "",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "C6 description",
                "CRE:id": "6",
                "CRE:name": "C6",
                "S1:hyperlink": "https://example.com/S1",
                "S1:link_type": "Linked To",
                "S1:section": "SE1",
                "S1:subsection": "SBE11",
                "S2:hyperlink": "https://example.com/S2",
                "S2:link_type": "Linked To",
                "S2:section": "SE2",
                "S2:subsection": "SBE22",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "7",
                "Linked_CRE_0:link_type": "Contains",
                "Linked_CRE_0:name": "C7",
                "Linked_CRE_1:id": "8",
                "Linked_CRE_1:link_type": "Contains",
                "Linked_CRE_1:name": "C8",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "",
                "CRE:id": "",
                "CRE:name": "",
                "S1:hyperlink": "",
                "S1:link_type": "",
                "S1:section": "",
                "S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "",
                "Linked_CRE_0:link_type": "",
                "Linked_CRE_0:name": "",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "https://example.com/SL",
                "SL:link_type": "",
                "SL:section": "SSL",
                "SL:subsection": "SBESL",
                "SL2:hyperlink": "",
                "SL2:link_type": "",
                "SL2:section": "",
                "SL2:subsection": "",
                "SLL:hyperlink": "",
                "SLL:link_type": "",
                "SLL:section": "",
                "SLL:subsection": "",
            },
            {
                "CRE:description": "",
                "CRE:id": "",
                "CRE:name": "",
                "S1:hyperlink": "",
                "S1:link_type": "",
                "S1:section": "",
                "S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "S3:hyperlink": "",
                "S3:link_type": "",
                "S3:section": "",
                "S3:subsection": "",
                "Linked_CRE_0:id": "",
                "Linked_CRE_0:link_type": "",
                "Linked_CRE_0:name": "",
                "Linked_CRE_1:id": "",
                "Linked_CRE_1:link_type": "",
                "Linked_CRE_1:name": "",
                "SL:hyperlink": "",
                "SL:link_type": "",
                "SL:section": "",
                "SL:subsection": "SESL",
                "SL2:hyperlink": "https://example.com/SL2",
                "SL2:link_type": "",
                "SL2:section": "SSL2",
                "SL2:subsection": "SBESL2",
                "SLL:hyperlink": "https://example.com/SLL",
                "SLL:link_type": "SAM",
                "SLL:section": "SSLL",
                "SLL:subsection": "SBESLL",
            },
        ]

        expected = {
            "C1": defs.CRE(
                id="1",
                description="C1 description",
                name="C1",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            subsection="SBE1",
                            hyperlink="https://example.com/S1",
                        ),
                    )
                ],
            ),
            "C2": defs.CRE(
                id="2",
                description="C2 description",
                name="C2",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="3", name="C3"),
                    )
                ],
            ),
            "C3": defs.CRE(
                id="3",
                description="C3 description",
                name="C3",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.PartOf,
                        document=defs.CRE(
                            id="2", description="C2 description", name="C2"
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S3",
                            section="SE3",
                            subsection="SBE3",
                            hyperlink="https://example.com/S3",
                        ),
                    ),
                ],
            ),
            "C5": defs.CRE(
                id="5",
                description="C5 description",
                name="C5",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            subsection="SBE1",
                            hyperlink="https://example.com/S1",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            subsection="SBE11",
                            hyperlink="https://example.com/S1",
                        ),
                    ),
                ],
            ),
            "C6": defs.CRE(
                id="6",
                description="C6 description",
                name="C6",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S2",
                            section="SE2",
                            subsection="SBE22",
                            hyperlink="https://example.com/S2",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            subsection="SBE11",
                            hyperlink="https://example.com/S1",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="7", name="C7"),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="8", name="C8"),
                    ),
                ],
            ),
            "C7": defs.CRE(
                id="7",
                name="C7",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.PartOf,
                        document=defs.CRE(
                            id="6", description="C6 description", name="C6"
                        ),
                    )
                ],
            ),
            "C8": defs.CRE(
                id="8",
                name="C8",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.PartOf,
                        document=defs.CRE(
                            id="6", description="C6 description", name="C6"
                        ),
                    )
                ],
            ),
            "SL2:SSL2": defs.Standard(
                name="SL2",
                section="SSL2",
                subsection="SBESL2",
                hyperlink="https://example.com/SL2",
            ),
            "SL:SSL": defs.Standard(
                name="SL",
                section="SSL",
                subsection="SBESL",
                hyperlink="https://example.com/SL",
            ),
            "SLL:SSLL": defs.Standard(
                name="SLL",
                section="SSLL",
                subsection="SBESLL",
                hyperlink="https://example.com/SLL",
            ),
        }

        result = parse_export_format(input_data)

        for key, val in result.items():
            # assert equal links, lists in python aren't ordered so normal equality doesn't work
            self.assertEqual(
                collections.Counter(expected[key].links), collections.Counter(val.links)
            )

            expected[key].links = []
            val.links = []

            self.assertDictEqual(val.todict(), expected[key].todict())

    def test_parse_uknown_key_val_spreadsheet(self) -> None:
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
                            doctype=defs.Credoctypes.Standard, name="CWE", section="598"
                        )
                    ),
                    defs.Link(
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard, name="CWE", section="384"
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
        actual = parse_uknown_key_val_spreadsheet(input_data)

        self.assertEqual(expected, actual)

    def test_parse_v0_standards(self) -> None:
        input_data = [
            {
                "CRE-ID-lookup-from-taxonomy-table": "011-040-026",
                "CS": "Session Management",
                "CWE": "598",
                "Description": "Verify the application never reveals session tokens in URL parameters or error messages.",
                "Development guide (does not exist for SessionManagement)": "",
                "ID-taxonomy-lookup-from-ASVS-mapping": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                "Item": "3.1.1",
                "Name": "Session",
                "OPC": "",
                "Top10 (lookup)": "https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                "WSTG": "WSTG-SESS-04",
            },
            {
                "CRE-ID-lookup-from-taxonomy-table": "011-040-033",
                "CS": "Session Management",
                "CWE": "384",
                "Description": "Verify the application generates a new session token on user "
                "authentication.",
                "Development guide (does not exist for SessionManagement)": "",
                "ID-taxonomy-lookup-from-ASVS-mapping": "SESSION-MGT-TOKEN-DIRECTIVES-GENERATION",
                "Item": "3.2.1",
                "Name": "Session",
                "OPC": "C6",
                "Top10 (lookup)": "",
                "WSTG": "WSTG-SESS-03",
            },
        ]
        expected = {
            "011-040-026": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                name="011-040-026",
                description="Verify the application never reveals session tokens in URL parameters or error messages.",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="ASVS",
                            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                            subsection="3.1.1",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="CS",
                            section="Session Management",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard, name="CWE", section="598"
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="Name",
                            section="Session",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="Top10 (lookup)",
                            section="https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="WSTG",
                            section="WSTG-SESS-04",
                        ),
                    ),
                ],
            ),
            "011-040-033": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                name="011-040-033",
                description="Verify the application generates a new session token on user authentication.",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="ASVS",
                            section="SESSION-MGT-TOKEN-DIRECTIVES-GENERATION",
                            subsection="3.2.1",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="CS",
                            section="Session Management",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard, name="CWE", section="384"
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="Name",
                            section="Session",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard, name="OPC", section="C6"
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="WSTG",
                            section="WSTG-SESS-03",
                        ),
                    ),
                ],
            ),
        }
        self.maxDiff = None
        output = parse_v0_standards(input_data)
        self.assertEqual(expected, output)

    def test_parse_v1_standards(self) -> None:

        input_data = [
            {
                "ASVS Item": "V9.9.9",
                "ASVS-L1": "X",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CORE-CRE-ID": "999-999",
                "CRE Group 1": "",
                "CRE Group 1 Lookup": "",
                "CRE Group 2": "",
                "CRE Group 2 Lookup": "",
                "CRE Group 3": "",
                "CRE Group 3 Lookup": "",
                "CRE Group 4": "",
                "CRE Group 4 Lookup": "",
                "CRE Group 5": "",
                "CRE Group 5 Lookup": "",
                "CRE Group 6": "",
                "CRE Group 6 Lookup": "",
                "CRE Group 7": "",
                "CRE Group 7 Lookup": "",
                "CWE": "",
                "Cheat Sheet": "",
                "Core-CRE (high-level description/summary)": "GROUPLESS",
                "Description": "groupless desc",
                "ID-taxonomy-lookup-from-ASVS-mapping": "",
                "NIST 800-53 - IS RELATED TO": "RA-3 RISK ASSESSMENT",
            },
            {
                "ASVS Item": "V1.1.2",
                "ASVS-L1": "X",
                "ASVS-L2": "X",
                "ASVS-L3": "X",
                "CORE-CRE-ID": "000-001",
                # group 1 maps to 2 cres
                "CRE Group 1": "SDLC_GUIDELINES_JUSTIFICATION",
                "CRE Group 1 Lookup": "925-827",
                # group 2 is invalid as it's imissing a lookup
                "CRE Group 2": "",
                "CRE Group 2 Lookup": "",
                "CRE Group 3": "",
                "CRE Group 3 Lookup": "",
                "CRE Group 4": "",
                "CRE Group 4 Lookup": "",
                "CRE Group 5": "",
                "CRE Group 5 Lookup": "",
                "CRE Group 6": "",
                "CRE Group 6 Lookup": "",
                "CRE Group 7": "",
                "CRE Group 7 Lookup": "",
                "CWE": "0",  # both CREs map to CWE 0
                # and they both map to the same cheatsheet
                "Cheat Sheet": "Architecture, Design and Threat Modeling Requirements",
                "Core-CRE (high-level description/summary)": "OTHER_CRE",
                "Description": "desc",
                "ID-taxonomy-lookup-from-ASVS-mapping": "SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                "NIST 800-53 - IS RELATED TO": "RA-3 RISK ASSESSMENT\n",
            },
            {
                "ASVS Item": "V1.1.1",
                "ASVS-L1": "",
                "ASVS-L2": "X",
                "ASVS-L3": "X",
                "CORE-CRE-ID": "002-036",
                "CRE Group 1": "SDLC_GUIDELINES_JUSTIFICATION",
                "CRE Group 1 Lookup": "925-827",
                "CRE Group 2": "REQUIREMENTS",
                "CRE Group 2 Lookup": "654-390",
                "CRE Group 3": "RISK_ANALYSIS",
                "CRE Group 3 Lookup": "533-658",
                "CRE Group 4": "THREAT_MODEL",
                "CRE Group 4 Lookup": "635-846",
                "CRE Group 5": "",
                "CRE Group 5 Lookup": "",
                "CRE Group 6": "",
                "CRE Group 6 Lookup": "",
                "CRE Group 7": "",
                "CRE Group 7 Lookup": "",
                "CWE": "0",
                "Cheat Sheet": "Architecture, Design and Threat Modeling Requirements",
                "Core-CRE (high-level description/summary)": "SDLC_APPLY_CONSISTENTLY",
                "Description": "Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                "ID-taxonomy-lookup-from-ASVS-mapping": "SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                "NIST 800-53 - IS RELATED TO": "RA-3 RISK ASSESSMENT\nPL-8 SECURITY AND PRIVACY ARCHITECTURES",
                "NIST 800-63": "None",
                "OPC": "C1",
                "SIG ISO 25010": "@SDLC",
                "Top10 2017": "",
                "WSTG": "",
                "cheat_sheets": "https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
            },
        ]

        groupless = {
            "GROUPLESS": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="999-999",
                description="groupless desc",
                name="GROUPLESS",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            doctype=defs.Credoctypes.Standard,
                            name="NIST 800-53",
                            tags=["is related to"],
                            section="RA-3 RISK ASSESSMENT",
                        ),
                    )
                ],
            )
        }

        expected = {
            "REQUIREMENTS": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="654-390",
                name="REQUIREMENTS",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            doctype=defs.Credoctypes.CRE,
                            id="002-036",
                            description="Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                            name="SDLC_APPLY_CONSISTENTLY",
                            links=[
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="ASVS",
                                        tags=["L2", "L3"],
                                        section="V1.1.1",
                                        subsection="SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="CWE",
                                        section="0",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="Cheatsheet",
                                        section="Architecture, Design and Threat Modeling Requirements",
                                        hyperlink="https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        links=[],
                                        tags=["is related to"],
                                        section="RA-3 RISK ASSESSMENT",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        links=[],
                                        tags=["is related to"],
                                        section="PL-8 SECURITY AND PRIVACY ARCHITECTURES",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="OPC",
                                        links=[],
                                        section="C1",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="SIG ISO 25010",
                                        section="@SDLC",
                                    ),
                                ),
                            ],
                        ),
                    )
                ],
            ),
            "RISK_ANALYSIS": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="533-658",
                name="RISK_ANALYSIS",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            doctype=defs.Credoctypes.CRE,
                            id="002-036",
                            description="Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                            name="SDLC_APPLY_CONSISTENTLY",
                            links=[
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="ASVS",
                                        tags=["L2", "L3"],
                                        section="V1.1.1",
                                        subsection="SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="CWE",
                                        links=[],
                                        section="0",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="Cheatsheet",
                                        section="Architecture, Design and Threat Modeling Requirements",
                                        hyperlink="https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        links=[],
                                        tags=["is related to"],
                                        section="RA-3 RISK ASSESSMENT",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        links=[],
                                        tags=["is related to"],
                                        section="PL-8 SECURITY AND PRIVACY ARCHITECTURES",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="OPC",
                                        links=[],
                                        section="C1",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="SIG ISO 25010",
                                        section="@SDLC",
                                    ),
                                ),
                            ],
                        ),
                    )
                ],
            ),
            "SDLC_GUIDELINES_JUSTIFICATION": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="925-827",
                name="SDLC_GUIDELINES_JUSTIFICATION",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            doctype=defs.Credoctypes.CRE,
                            id="000-001",
                            description="desc",
                            name="OTHER_CRE",
                            links=[
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="ASVS",
                                        tags=["L1", "L2", "L3"],
                                        section="V1.1.2",
                                        subsection="SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="CWE",
                                        section="0",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        tags=["is related to"],
                                        section="RA-3 RISK ASSESSMENT",
                                    ),
                                ),
                            ],
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            doctype=defs.Credoctypes.CRE,
                            id="002-036",
                            description="Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                            name="SDLC_APPLY_CONSISTENTLY",
                            links=[
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="ASVS",
                                        tags=["L2", "L3"],
                                        section="V1.1.1",
                                        subsection="SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="CWE",
                                        section="0",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="Cheatsheet",
                                        section="Architecture, Design and Threat Modeling Requirements",
                                        hyperlink="https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        tags=["is related to"],
                                        section="RA-3 RISK ASSESSMENT",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        tags=["is related to"],
                                        section="PL-8 SECURITY AND PRIVACY ARCHITECTURES",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="OPC",
                                        section="C1",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="SIG ISO 25010",
                                        section="@SDLC",
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            "THREAT_MODEL": defs.CRE(
                doctype=defs.Credoctypes.CRE,
                id="635-846",
                name="THREAT_MODEL",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            doctype=defs.Credoctypes.CRE,
                            id="002-036",
                            description="Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                            name="SDLC_APPLY_CONSISTENTLY",
                            links=[
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="ASVS",
                                        tags=["L2", "L3"],
                                        section="V1.1.1",
                                        subsection="SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="CWE",
                                        section="0",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="Cheatsheet",
                                        section="Architecture, Design and Threat Modeling Requirements",
                                        hyperlink="https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        tags=["is related to"],
                                        section="RA-3 RISK ASSESSMENT",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="NIST 800-53",
                                        links=[],
                                        tags=["is related to"],
                                        section="PL-8 SECURITY AND PRIVACY ARCHITECTURES",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="OPC",
                                        section="C1",
                                    ),
                                ),
                                defs.Link(
                                    ltype=defs.LinkTypes.LinkedTo,
                                    document=defs.Standard(
                                        doctype=defs.Credoctypes.Standard,
                                        name="SIG ISO 25010",
                                        section="@SDLC",
                                    ),
                                ),
                            ],
                        ),
                    )
                ],
            ),
        }

        self.maxDiff = None
        output = parse_v1_standards(input_data)
        for key, value in output[0].items():
            self.assertEqual(
                collections.Counter(value.links),
                collections.Counter(expected[key].links),
            )
            expected[key].links = []
            value.links = []
            self.assertEqual(expected[key], value)
        for key, value in output[1].items():
            self.assertEqual(
                collections.Counter(value.links),
                collections.Counter(groupless[key].links),
            )
            value.links = []
            groupless[key].links = []
            self.assertEqual(groupless[key], value)

    def test_parse_hierarchical_export_format(self) -> None:
        #  todo add a tags linking test
        ctag = defs.CRE(id="123", name="tag-connection")
        cauth = defs.CRE(id=8, name="Authentication", tags=["tag-connection"])
        cauthmech = defs.CRE(id=3, name="Authentication mechanism")

        cauth4 = defs.CRE(
            id=4,
            name="Verify that the application uses a single vetted authentication mechanism",
            tags=[],
        )
        clogging = defs.CRE(name="Logging and Error handling")
        cfp = defs.CRE(name="FooParent")
        sTop10 = defs.Standard(
            hyperlink="https://example.com/top102017",
            name="Top10 2017",
            section="A2_Broken_Authentication",
        )

        sOPC = defs.Standard(
            name="OPC", section="123654", hyperlink="https://example.com/opc"
        )
        sCWE19876 = defs.Standard(
            name="CWE", section="19876", hyperlink="https://example.com/cwe19876"
        )
        sWSTG = defs.Standard(
            name="WSTG", section="2.1.2.3", hyperlink="https://example.com/wstg"
        )
        sNIST4 = defs.Standard(name="NIST 800-63", section="4444")
        sNIST3 = defs.Standard(name="NIST 800-63", section="3333")
        sNIST53 = defs.Standard(
            name="NIST 800-53 v5",
            section="SA-22 Unsupported System Components",
            hyperlink="https://example.com/nist-800-53-v5",
        )
        sASVS = defs.Standard(
            name="ASVS", section="V1.2.3", hyperlink="https://example.com/asvs"
        )
        sCWE = defs.Standard(
            name="CWE", section="306", hyperlink="https://example.com/cwe306"
        )
        scheatf = defs.Standard(
            name="Cheat_sheets",
            section="foo",
            hyperlink="https://example.com/cheatsheetf/foo",
        )
        scheatb = defs.Standard(
            name="Cheat_sheets",
            section="bar",
            hyperlink="https://example.com/cheatsheetb/bar",
        )

        cfoo = (
            defs.CRE(id=9, name="FooBar")
            .add_link(
                defs.Link(
                    ltype=defs.LinkTypes.Related, document=cauthmech.shallow_copy()
                )
            )
            .add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=scheatb))
            .add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=scheatf))
        )
        cfp.add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cfoo.shallow_copy())
        )
        cauth.add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=cfoo.shallow_copy())
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cauthmech.shallow_copy())
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sTop10)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sNIST3)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sNIST4)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sWSTG)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sCWE19876)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sOPC)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sNIST53)
        ).add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=ctag)
        )

        cauthmech.add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cauth4.shallow_copy())
        )

        cauth4.add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=clogging.shallow_copy())
        ).add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sASVS)).add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=sCWE)
        )

        for nsection in [
            "PL-8 Information Security Architecture",
            "SC-39 PROCESS ISOLATION",
            "SC-3 SECURITY FUNCTION",
        ]:
            cauth4.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="NIST 800-53 v5",
                        section=nsection,
                        hyperlink="https://example.com/nist-800-53-v5",
                    ),
                )
            )

        data = [
            {
                "Standard ASVS Item": "",
                "ASVS sequence": 0,
                "Standard ASVS Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top10 2017": "A2_Broken_Authentication",
                "Standard Top10 Hyperlink": "https://example.com/top102017",
                "CRE ID": "",
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST 800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS Item": "",
                "ASVS sequence": 0,
                "Standard ASVS Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "tag-connection",
                "Standard Top10 2017": "",
                "Standard Top10 Hyperlink": "",
                "CRE ID": "123",
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST 800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS Item": "",
                "ASVS sequence": 0,
                "Standard ASVS Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top10 2017": "A2_Broken_Authentication",
                "Standard Top10 Hyperlink": "https://example.com/top102017",
                "CRE ID": 8,
                "Standard CWE (from ASVS)": "19876",
                "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe19876",
                "Link to other CRE": "FooBar",
                "Standard NIST 800-53 v5": "SA-22 Unsupported System Components",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "4444/3333",
                "Standard OPC (ASVS source)": "123654",
                "Standard OPC (ASVS source)-hyperlink": "https://example.com/opc",
                "CRE Tags": "tag-connection",
                "Standard WSTG": "2.1.2.3",
                "Standard WSTG-Hyperlink": "https://example.com/wstg",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS Item": "",
                "ASVS sequence": 0,
                "Standard ASVS Hyperlink": "https://example.com",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "Authentication mechanism",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "",
                "Standard Top10 2017": "See higher level topic",
                "Standard Top10 Hyperlink": "https://example.com/top102017",
                "CRE ID": 3,
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "1111",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS Item": "V1.2.3",
                "ASVS sequence": 10,
                "Standard ASVS Hyperlink": "https://example.com/asvs",
                "ASVS-L1": "",
                "ASVS-L2": "X",
                "ASVS-L3": "X",
                "CRE hierarchy 1": "Authentication",
                "CRE hierarchy 2": "Authentication mechanism",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "Verify that the application uses a single vetted authentication mechanism",
                "Standard Top10 2017": "See higher level topic",
                "Standard Top10 Hyperlink": "https://example.com/top102017",
                "CRE ID": 4,
                "Standard CWE (from ASVS)": 306,
                "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe306",
                "Link to other CRE": "Logging and Error handling",
                "Standard NIST 800-53 v5": "PL-8 Information Security Architecture\n"
                "SC-39 PROCESS ISOLATION\n"
                "SC-3 SECURITY FUNCTION",
                "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5",
                "Standard NIST-800-63 (from ASVS)": "None",
                "Standard OPC (ASVS source)": "None",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "",
                "Standard Cheat_sheets-Hyperlink": "",
            },
            {
                "Standard ASVS Item": "",
                "ASVS sequence": 0,
                "Standard ASVS Hyperlink": "",
                "ASVS-L1": "",
                "ASVS-L2": "",
                "ASVS-L3": "",
                "CRE hierarchy 1": "FooParent",
                "CRE hierarchy 2": "",
                "CRE hierarchy 3": "",
                "CRE hierarchy 4": "FooBar",
                "Standard Top10 2017": "",
                "Standard Top10 Hyperlink": "",
                "CRE ID": 9,
                "Standard CWE (from ASVS)": "",
                "Standard CWE (from ASVS)-hyperlink": "",
                "Link to other CRE": "Authentication mechanism",
                "Standard NIST 800-53 v5": "",
                "Standard NIST 800-53 v5-hyperlink": "",
                "Standard NIST-800-63 (from ASVS)": "",
                "Standard OPC (ASVS source)": "",
                "Standard OPC (ASVS source)-hyperlink": "",
                "CRE Tags": "",
                "Standard WSTG": "",
                "Standard WSTG-Hyperlink": "",
                "Standard Cheat_sheets": "foo; bar",
                "Standard Cheat_sheets-Hyperlink": "https://example.com/cheatsheetf/foo; https://example.com/cheatsheetb/bar",
            },
        ]
        expected = {
            "FooParent": cfp,
            "FooBar": cfoo,
            "Authentication": cauth,
            "Authentication mechanism": cauthmech,
            "Verify that the application uses a single vetted authentication mechanism": cauth4,
            "Logging and Error handling": clogging,
        }

        self.maxDiff = None
        output = parse_hierarchical_export_format(data)
        for k, v in expected.items():
            try:

                self.assertEqual(
                    collections.Counter(output[k].links), collections.Counter(v.links)
                )
                self.assertEqual(output[k], v)
            except Exception as e:
                print("*" * 88)
                pprint(output[k].todict())
                print("*" * 88)
                pprint(v.todict())
                print("*" * 88)
                print("*" * 88)
                raise e


if __name__ == "__main__":
    unittest.main()
