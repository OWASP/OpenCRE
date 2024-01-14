import collections
import unittest
from pprint import pprint

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
        input_data = [
            {
                "CRE:description": "C1 description",
                "CRE:id": "1",
                "CRE:name": "C1",
                "Standard:S1:hyperlink": "https://example.com/S1",
                "Standard:S1:link_type": "Linked To",
                "Standard:S1:section": "SE1",
                "Standard:S1:subsection": "SBE1",
                "Tool:S2:hyperlink": "",
                "Tool:S2:link_type": "",
                "Tool:S2:description": "",
                "Tool:S2:ToolType": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "",
                "Standard:S1:link_type": "",
                "Standard:S1:section": "",
                "Standard:S1:subsection": "",
                "Tool:S2:hyperlink": "",
                "Tool:S2:link_type": "",
                "Tool:S2:description": "",
                "Tool:S2:ToolType": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "",
                "Standard:S1:link_type": "",
                "Standard:S1:section": "",
                "Standard:S1:subsection": "",
                "Tool:S2:hyperlink": "",
                "Tool:S2:link_type": "",
                "Tool:S2:description": "",
                "Tool:S2:ToolType": "",
                "Code:S3:hyperlink": "https://example.com/S3",
                "Code:S3:link_type": "Linked To",
                "Code:S3:description": "SE3",
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
                "Standard:S1:hyperlink": "https://example.com/S1",
                "Standard:S1:link_type": "Linked To",
                "Standard:S1:section": "SE1",
                "Standard:S1:subsection": "SBE1",
                "Tool:S2:hyperlink": "",
                "Tool:S2:link_type": "",
                "Tool:S2:description": "",
                "Tool:S2:ToolType": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "https://example.com/S1",
                "Standard:S1:link_type": "Linked To",
                "Standard:S1:section": "SE1",
                "Standard:S1:subsection": "SBE11",
                "Tool:S2:hyperlink": "",
                "Tool:S2:link_type": "",
                "Tool:S2:description": "",
                "Tool:S2:ToolType": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "https://example.com/S1",
                "Standard:S1:link_type": "Linked To",
                "Standard:S1:section": "SE1",
                "Standard:S1:subsection": "SBE11",
                "Tool:S2:hyperlink": "https://example.com/S2",
                "Tool:S2:link_type": "Linked To",
                "Tool:S2:description": "SE2",
                "Tool:S2:ToolType": "Offensive",
                "Tool:S2:SectionID": "0",
                "Tool:S2:section": "rule-0",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "",
                "Standard:S1:link_type": "",
                "Standard:S1:section": "",
                "Standard:S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                "Standard:S1:hyperlink": "",
                "Standard:S1:link_type": "",
                "Standard:S1:section": "",
                "Standard:S1:subsection": "",
                "S2:hyperlink": "",
                "S2:link_type": "",
                "S2:section": "",
                "S2:subsection": "",
                "Code:S3:hyperlink": "",
                "Code:S3:link_type": "",
                "Code:S3:description": "",
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
                        document=defs.Code(
                            name="S3",
                            description="SE3",
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
                        document=defs.Tool(
                            name="S2",
                            section="rule-0",
                            sectionID="0",
                            tooltype=defs.ToolTypes.Offensive,
                            description="SE2",
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
        
        # register cres
        ctag = defs.CRE(id="123", name="tag-connection")
        cauth = defs.CRE(id=8, name="Authentication", tags=["tag-connection"])
        cauthmech = defs.CRE(id=3, name="Authentication mechanism")
        cauth_verify = defs.CRE(id=4,tags=[],name="Verify that the application uses a single vetted authentication mechanism")
        clogging = defs.CRE(name="Logging and Error handling")
        cfp = defs.CRE(name="FooParent")
        cfoo = defs.CRE(id=9, name="FooBar")

        # register standards
        s_top10_2017_a2 = defs.Standard(
            hyperlink="https://example.com/top102017",
            name="OWASP Top 10 2017",
            section="A2_Broken_Authentication",
        )

        s_opc_123654 = defs.Standard(
            name="OWASP Proactive Controls",
            section="123654",
            hyperlink="https://example.com/opc",
        )
        s_cwe_19876 = defs.Standard(
            name="CWE", sectionID="19876", hyperlink="https://example.com/cwe19876"
        )
        s_cwe_306 = defs.Standard(
            name="CWE", sectionID="306", hyperlink="https://example.com/cwe306"
        )
        s_wstg_2123 = defs.Standard(
            name="OWASP Web Security Testing Guide (WSTG)",
            section="2.1.2.3",
            hyperlink="https://example.com/wstg",
        )
        s_asvs_10 = defs.Standard(
            name="ASVS",
            section="10",
            sectionID="V1.2.3",
            hyperlink="https://example.com/asvs",
        )

        s_cheatsheet_f = defs.Standard(
            name="OWASP Cheat Sheets",
            section="foo",
            hyperlink="https://example.com/cheatsheetf/foo",
        )
        s_cheatsheet_b = defs.Standard(
            name="OWASP Cheat Sheets",
            section="bar",
            hyperlink="https://example.com/cheatsheetb/bar",
        )
        s_nist_63_4 = defs.Standard(name="NIST 800-63", section="4444")
        s_nist_63_3 = defs.Standard(name="NIST 800-63", section="3333")

        s_nist_53_sa22 = defs.Standard(
            name="NIST 800-53 v5",
            section="SA-22 Unsupported System Components",
            hyperlink="https://example.com/nist-800-53-v5",
        )
        s_nist_53_pl8 = defs.Standard(
                name="NIST 800-53 v5",
                section="PL-8 Information Security Architecture",
                hyperlink="https://example.com/nist-800-53-v5",
            )
        s_nist_53_sc39 = defs.Standard(
                name="NIST 800-53 v5",
                section="SC-39 PROCESS ISOLATION",
                hyperlink="https://example.com/nist-800-53-v5",
            )
        s_nist_53_sc3 = defs.Standard(
                name="NIST 800-53 v5",
                section="SC-3 SECURITY FUNCTION",
                hyperlink="https://example.com/nist-800-53-v5",
            )

    # cre links AKA semantic graph structure
        cfoo.add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=cauthmech.shallow_copy()))
        cfp.add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cfoo.shallow_copy()))
       
        cauth.add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=cfoo.shallow_copy())
            ).add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cauthmech.shallow_copy())
            ).add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=ctag))
        
        cauthmech.add_link(
            defs.Link(ltype=defs.LinkTypes.Contains, document=cauth_verify.shallow_copy()))
        cauth_verify.add_link(
            defs.Link(ltype=defs.LinkTypes.Related, document=clogging.shallow_copy()))

        # standard links AKA semantic web content
        s_cheatsheet_b.add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cfoo.shallow_copy()))
        s_cheatsheet_f.add_link(
            defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cfoo.shallow_copy()))
        s_top10_2017_a2.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_nist_63_3.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_nist_63_4.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_wstg_2123.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_cwe_19876.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_opc_123654.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_nist_53_sa22.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_asvs_10.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))
        s_cwe_306.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cauth))

        s_nist_53_pl8.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo,document=cauth_verify,))
        s_nist_53_sc39.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo,document=cauth_verify,))
        s_nist_53_sc3.add_link(defs.Link(ltype=defs.LinkTypes.LinkedTo,document=cauth_verify,))

        expected = {
            defs.Credoctypes.CRE.value: [ctag,cauth,cauthmech,cauth_verify,clogging,cfp,cfoo],
            "NIST 800-53 v5": [s_nist_53_pl8,s_nist_53_sa22,s_nist_53_sc39,s_nist_53_sc3],
            "NIST 800-63":[s_nist_63_3,s_nist_63_4],
            "OWASP Cheat Sheets": [s_cheatsheet_b,s_cheatsheet_f],
            "OWASP Top 10 2017": [s_top10_2017_a2],
            "OWASP Proactive Controls": [s_opc_123654],
            "CWE": [s_cwe_19876,s_cwe_306],
            "OWASP Web Security Testing Guide (WSTG)": [s_wstg_2123],
            "ASVS": [s_asvs_10],
        }

        output = parse_hierarchical_export_format(hierarchical_export_format)
        self.maxDiff = None
        for k, v in expected.items():
            try:
                self.assertEqual(output[k], v)
            except Exception as e:
                pprint("-" * 45+f" {k} "+"-"*45)
                pprint(k)
                pprint(output[k])
                pprint("-" * 90)
                pprint(v)
                pprint("-" * 90)
                raise e
        for k, v in output.items():
            try:
                self.assertEqual(expected[k], v)
            except Exception as e:
                pprint("-" * 45+f" {k} "+"-"*45)
                pprint(expected[k])
                pprint("-" * 90)
                pprint(v)
                pprint("-" * 90)
                raise e


hierarchical_export_format = [
    {
        "Standard ASVS 4.0.3 Item": "",
        "Standard ASVS 4.0.3 description": "",
        "Standard ASVS 4.0.3 Hyperlink": "",
        "ASVS-L1": "",
        "ASVS-L2": "",
        "ASVS-L3": "",
        "CRE hierarchy 1": "",
        "CRE hierarchy 2": "",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "",
        "Standard Top 10 2017 item": "A2_Broken_Authentication",
        "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
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
        "Standard WSTG-item": "",
        "Standard WSTG-Hyperlink": "",
        "Standard Cheat_sheets": "",
        "Standard Cheat_sheets-Hyperlink": "",
    },
    {
        "Standard ASVS 4.0.3 Item": "",
        "Standard ASVS 4.0.3 description": "",
        "Standard ASVS 4.0.3 Hyperlink": "",
        "ASVS-L1": "",
        "ASVS-L2": "",
        "ASVS-L3": "",
        "CRE hierarchy 1": "",
        "CRE hierarchy 2": "",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "tag-connection",
        "Standard Top 10 2017 item": "",
        "Standard Top 10 2017 Hyperlink": "",
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
        "Standard WSTG-item": "",
        "Standard WSTG-Hyperlink": "",
        "Standard Cheat_sheets": "",
        "Standard Cheat_sheets-Hyperlink": "",
    },
    {
        "Standard ASVS 4.0.3 Item": "",
        "Standard ASVS 4.0.3 description": "",
        "Standard ASVS 4.0.3 Hyperlink": "",
        "ASVS-L1": "",
        "ASVS-L2": "",
        "ASVS-L3": "",
        "CRE hierarchy 1": "Authentication",
        "CRE hierarchy 2": "",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "",
        "Standard Top 10 2017 item": "A2_Broken_Authentication",
        "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
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
        "Standard WSTG-item": "2.1.2.3",
        "Standard WSTG-Hyperlink": "https://example.com/wstg",
        "Standard Cheat_sheets": "",
        "Standard Cheat_sheets-Hyperlink": "",
    },
    {
        "Standard ASVS 4.0.3 Item": "",
        "Standard ASVS 4.0.3 description": "",
        "Standard ASVS 4.0.3 Hyperlink": "",
        "ASVS-L1": "",
        "ASVS-L2": "",
        "ASVS-L3": "",
        "CRE hierarchy 1": "Authentication",
        "CRE hierarchy 2": "Authentication mechanism",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "",
        "Standard Top 10 2017 item": "See higher level topic",
        "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
        "CRE ID": 3,
        "Standard CWE (from ASVS)": "",
        "Standard CWE (from ASVS)-hyperlink": "",
        "Link to other CRE": "",
        "Standard NIST 800-53 v5": "",
        "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
        "Standard NIST-800-63 (from ASVS)": "",
        "Standard OPC (ASVS source)": "",
        "Standard OPC (ASVS source)-hyperlink": "",
        "CRE Tags": "",
        "Standard WSTG-item": "",
        "Standard WSTG-Hyperlink": "",
        "Standard Cheat_sheets": "",
        "Standard Cheat_sheets-Hyperlink": "",
    },
    {
        "Standard ASVS 4.0.3 Item": "V1.2.3",
        "Standard ASVS 4.0.3 description": 10,
        "Standard ASVS 4.0.3 Hyperlink": "https://example.com/asvs",
        "ASVS-L1": "",
        "ASVS-L2": "X",
        "ASVS-L3": "X",
        "CRE hierarchy 1": "Authentication",
        "CRE hierarchy 2": "Authentication mechanism",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "Verify that the application uses a single vetted authentication mechanism",
        "Standard Top 10 2017 item": "See higher level topic",
        "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
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
        "Standard WSTG-item": "",
        "Standard WSTG-Hyperlink": "",
        "Standard Cheat_sheets": "",
        "Standard Cheat_sheets-Hyperlink": "",
    },
    {
        "Standard ASVS 4.0.3 Item": "",
        "Standard ASVS 4.0.3 description": "",
        "Standard ASVS 4.0.3 Hyperlink": "",
        "ASVS-L1": "",
        "ASVS-L2": "",
        "ASVS-L3": "",
        "CRE hierarchy 1": "FooParent",
        "CRE hierarchy 2": "",
        "CRE hierarchy 3": "",
        "CRE hierarchy 4": "FooBar",
        "Standard Top 10 2017 item": "",
        "Standard Top 10 2017 Hyperlink": "",
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
        "Standard WSTG-item": "",
        "Standard WSTG-Hyperlink": "",
        "Standard Cheat_sheets": "foo; bar",
        "Standard Cheat_sheets-Hyperlink": "https://example.com/cheatsheetf/foo; https://example.com/cheatsheetb/bar",
    },
]
if __name__ == "__main__":
    unittest.main()
