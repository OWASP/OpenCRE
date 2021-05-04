import unittest
from pprint import pprint

from application.defs import cre_defs as defs
from application.utils.parsers import *


class TestCreDefs(unittest.TestCase):
    def test_document_to_dict(self):
        standard = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
        )
        standard_output = {
            "doctype": "Standard",
            "hyperlink": None,
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
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
                        "hyperlink": None,
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
                                    "hyperlink": None,
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
                        "hyperlink": None,
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
            "hyperlink": None,
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
        }

        self.assertEqual(standard.todict(), standard_output)

        self.assertEqual(cre.todict(), cre_output)
        self.assertEqual(group.todict(), group_output)
        self.assertEqual(nested.todict(), nested_output)


if __name__ == "__main__":
    unittest.main()
