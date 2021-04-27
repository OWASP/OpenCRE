import unittest
from defs import cre_defs as defs
from utils.parsers import *
from pprint import pprint
from database import db
from cre_main import *


class TestMain(unittest.TestCase):
    def setUp(self):
        connection = ""  # empty string means temporary db
        collection = db.Standard_collection(cache_file=connection)
        self.collection = collection

    def test_register_standard_with_links(self):
        standard_with_links = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with_links",
            links=[
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="CWE",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                        section="598",
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="ASVS",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                        section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    )
                ),
            ],
            tags=[],
            metadata=defs.Metadata(labels=[]),
            section="Standard With Links",
        )
        ret = register_standard(
            standard=standard_with_links, collection=self.collection
        )
        # assert returned value makes sense
        self.assertEqual(ret.name, "standard_with_links")
        self.assertEqual(ret.section, "Standard With Links")

        # assert db structure makes sense
        # no links since our standards don't have a CRE to map to
        self.assertEqual(self.collection.session.query(db.Links).all(), [])
        # 3 cre-less standards in the db
        self.assertEqual(len(self.collection.session.query(db.Standard).all()), 3)

    def test_register_standard_with_cre(self):

        standard_with_cre = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with_cre",
            links=[
                defs.Link(
                    document=defs.CRE(
                        doctype=defs.Credoctypes.CRE,
                        id="",
                        description="cre desc",
                        name="crename",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="ASVS",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                        section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    )
                ),
            ],
            tags=[],
            metadata=defs.Metadata(labels=[]),
            section="standard_with_cre",
        )

        ret = register_standard(standard=standard_with_cre, collection=self.collection)
        # assert db structure makes sense
        self.assertEqual(
            len(self.collection.session.query(db.Links).all()), 2
        )  # 2 links in the db
        self.assertEqual(
            len(self.collection.session.query(db.Standard).all()), 2
        )  # 2 standards in the db
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 1
        )  # 1 cre in the db

    def test_register_standard_with_groupped_cre_links(self):
        with_groupped_cre_links = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            id="",
            description="",
            name="standard_with",
            links=[
                defs.Link(
                    document=defs.CRE(
                        id="",
                        description="group desc",
                        name="group name",
                        links=[
                            defs.Link(
                                document=defs.CRE(
                                    doctype=defs.Credoctypes.CRE,
                                    id="101-001",
                                    description="cre2 desc",
                                    name="crename2",
                                    links=[],
                                    tags=[],
                                    metadata=defs.Metadata(labels=[]),
                                )
                            )
                        ],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="CWE",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                        section="598",
                    )
                ),
                defs.Link(
                    document=defs.CRE(
                        doctype=defs.Credoctypes.CRE,
                        id="",
                        description="cre desc",
                        name="crename",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="ASVS",
                        links=[],
                        tags=[],
                        metadata=defs.Metadata(labels=[]),
                        section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                    )
                ),
            ],
            tags=[],
            metadata=defs.Metadata(labels=[]),
            section="Session Management",
        )

        ret = register_standard(
            standard=with_groupped_cre_links, collection=self.collection
        )
        # assert db structure makes sense
        self.assertEqual(
            len(self.collection.session.query(db.Links).all()), 5
        )  # 5 links in the db

        self.assertEqual(
            len(self.collection.session.query(db.InternalLinks).all()), 1
        )  # 1 internal link in the db

        self.assertEqual(
            len(self.collection.session.query(db.Standard).all()), 3
        )  # 3 standards in the db
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 3
        )  # 2 cres in the db

    def test_register_cre(self):
        standard = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
        )
        cre = defs.CRE(
            id="100",
            description="CREdesc",
            name="CREname",
            links=[defs.Link(document=standard)],
            tags=["CREt1", "CREt2"],
            metadata=defs.Metadata(labels=["CREl1", "CREl2"]),
        )
        self.assertEqual(register_cre(cre, self.collection).name, cre.name)
        self.assertEqual(register_cre(cre, self.collection).external_id, cre.id)
        self.assertEqual(
            len(self.collection.session.query(db.CRE).all()), 1
        )  # 1 cre in the db

    def test_parse_file(self):
        file = {
            "description": "Verify that approved cryptographic algorithms are used in the generation, seeding, and verification.",
            "doctype": "CRE",
            "id": "001-005-073",
            "links": [
                {
                    "type": "SAM",
                    "tags": [],
                    "document": {
                        "description": "",
                        "doctype": "Standard",
                        "hyperlink": "None",
                        "id": "",
                        "links": [],
                        "metadata": {},
                        "name": "TOP10",
                        "section": "https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        "subsection": "None",
                        "tags": [],
                    },
                },
                {
                    "type": "SAM",
                    "tags": [],
                    "document": {
                        "description": "",
                        "doctype": "Standard",
                        "hyperlink": "None",
                        "id": "",
                        "links": [],
                        "metadata": {},
                        "name": "ISO 25010",
                        "section": "Secure data storage",
                        "subsection": "None",
                        "tags": [],
                    },
                },
            ],
            "metadata": {},
            "name": "CREDENTIALS_MANAGEMENT_CRYPTOGRAPHIC_DIRECTIVES",
            "tags": [],
        }
        expected = defs.CRE(
            doctype=defs.Credoctypes.CRE,
            id="001-005-073",
            description="Verify that approved cryptographic algorithms are used in the generation, seeding, and verification.",
            name="CREDENTIALS_MANAGEMENT_CRYPTOGRAPHIC_DIRECTIVES",
            links=[
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="TOP10",
                        links=[],
                        tags=[],
                        metadata={},
                        section="https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control",
                        subsection="None",
                        hyperlink="None",
                    )
                ),
                defs.Link(
                    document=defs.Standard(
                        doctype=defs.Credoctypes.Standard,
                        id="",
                        description="",
                        name="ISO 25010",
                        links=[],
                        tags=[],
                        metadata={},
                        section="Secure data storage",
                        subsection="None",
                        hyperlink="None",
                    )
                ),
            ],
            tags=[],
            metadata={},
        )

        result = parse_file(file, self.collection)

        self.assertEqual(result, expected)

    # TODO: ensure db has exact values instead of correct number of elements
    def test_parse_standards_from_spreadsheeet(self):
        input = [
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
                "CWE": 0,
                "Cheat Sheet": "Architecture, Design and Threat Modeling Requirements",
                "Core-CRE (high-level description/summary)": "SDLC_APPLY_CONSISTENTLY",
                "Description": "Verify the use of a secure software development lifecycle that addresses security in all stages of development. (C1)",
                "ID-taxonomy-lookup-from-ASVS-mapping": "SDLC_GUIDELINES_JUSTIFICATION-REQUIREMENTS-RISK_ANALYSIS-THREAT_MODEL",
                "NIST 800-53 - IS RELATED TO": "RA-3 RISK ASSESSMENT,\n"
                "PL-8 SECURITY AND PRIVACY ARCHITECTURES",
                "NIST 800-63": "None",
                "OPC": "C1",
                "SIG ISO 25010": "@SDLC",
                "Top10 2017": "",
                'UNIQUE IDs\n\nRandom CRE-ID PER ASVS\n=concatenate(randbetween(100,999),"-",randbetween(100,999))': "418-852",
                "WSTG": "test",
                "cheat_sheets": "https: // cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html, https: // cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html",
            }
        ]
        parse_standards_from_spreadsheeet(input, self.collection)
        self.assertEqual(len(self.collection.session.query(db.Standard).all()), 8)
        self.assertEqual(len(self.collection.session.query(db.CRE).all()), 5)
        # assert the one CRE in the inpu externally links to all the 8 standards
        self.assertEqual(len(self.collection.session.query(db.Links).all()), 8)
        self.assertEqual(len(self.collection.session.query(db.InternalLinks).all()), 4)

    # TODO:implement
    #  def test_get_standards_files_from_disk(self):
    #     raise NotImplementedError

    # def test_add_from_spreadsheet(self):
    #     raise NotImplementedError

    # def test_add_from_disk(self):
    #     raise NotImplementedError

    # def test_review_from_spreadsheet(self):
    #     raise NotImplementedError

    # def test_review_from_disk(self):
    #     raise NotImplementedError

    # def test_prepare_for_review(self):
    #     raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
