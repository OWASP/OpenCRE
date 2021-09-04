import unittest

from application.defs import cre_defs as defs


class TestCreDefs(unittest.TestCase):
    def test_document_to_dict(self) -> None:
        standard = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
            version="0.0.0",
        )
        standard_output = {
            "doctype": "Standard",
            "hyperlink": "",
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
            "version": "0.0.0",
        }

        cre = defs.CRE(
            id="100",
            description="CREdesc",
            name="CREname",
            links=[defs.Link(document=standard)],
            tags=["CREt1", "CREt2"],
        )
        cre_output = {
            "description": "CREdesc",
            "doctype": "CRE",
            "id": "100",
            "links": [
                {
                    "type": "SAM",
                    "document": {
                        "doctype": "Standard",
                        "hyperlink": "",
                        "name": "ASVS",
                        "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                        "subsection": "3.1.1",
                    },
                }
            ],
            "name": "CREname",
            "tags": ["CREt1", "CREt2"],
        }

        standard2 = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="Standard",
            section="StandardSection",
            subsection="3.1.1",
        )
        group = defs.CRE(
            id="500",
            description="desc",
            name="name",
            links=[defs.Link(document=cre), defs.Link(document=standard2)],
            tags=["tag1", "t2"],
        )
        group_output = {
            "description": "desc",
            "doctype": "CRE",
            "id": "500",
            "links": [
                {
                    "type": "SAM",
                    "document": {
                        "description": "CREdesc",
                        "doctype": "CRE",
                        "id": "100",
                        "links": [
                            {
                                "type": "SAM",
                                "document": {
                                    "doctype": "Standard",
                                    "hyperlink": "",
                                    "name": "ASVS",
                                    "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                                    "subsection": "3.1.1",
                                },
                            }
                        ],
                        "name": "CREname",
                        "tags": ["CREt1", "CREt2"],
                    },
                },
                {
                    "type": "SAM",
                    "document": {
                        "doctype": "Standard",
                        "hyperlink": "",
                        "name": "Standard",
                        "section": "StandardSection",
                        "subsection": "3.1.1",
                    },
                },
            ],
            "name": "name",
            "tags": ["tag1", "t2"],
        }
        nested = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
        )
        nested_output = {
            "doctype": "Standard",
            "hyperlink": "",
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
            "version": "",
        }
        self.maxDiff = None
        self.assertEqual(standard.todict(), standard_output)

        self.assertCountEqual(cre.todict(), cre_output)
        self.assertCountEqual(group.todict(), group_output)
        self.assertCountEqual(nested.todict(), nested_output)

    def test_linktype_from_str(self) -> None:
        expected = {
            "SAME": defs.LinkTypes.Same,
            "SAM": defs.LinkTypes.Same,
            "Linked To": defs.LinkTypes.LinkedTo,
            "Is Part Of": defs.LinkTypes.PartOf,
            "Contains": defs.LinkTypes.Contains,
            "Related": defs.LinkTypes.Related,
        }
        for ke, val in expected.items():
            self.assertEqual(defs.LinkTypes.from_str(ke), val)
        with self.assertRaises(KeyError):
            defs.LinkTypes.from_str("asdf")


if __name__ == "__main__":
    unittest.main()
