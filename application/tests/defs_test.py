import copy
import unittest
from dataclasses import asdict
from pprint import pprint
from typing import Set

import dacite
from application.defs import cre_defs as defs
from dacite import Config, from_dict


class TestCreDefs(unittest.TestCase):
    def test_document_todict(self) -> None:
        standard = defs.Standard(
            doctype=defs.Credoctypes.Standard,
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
            version="0.0.0",
        )
        standard_output = {
            "doctype": "Standard",
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
                    "ltype": "SAME",
                    "document": {
                        "doctype": "Standard",
                        "name": "ASVS",
                        "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                        "subsection": "3.1.1",
                        "version": "0.0.0",
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
                    "ltype": "SAME",
                    "document": {
                        "description": "CREdesc",
                        "doctype": "CRE",
                        "id": "100",
                        "links": [
                            {
                                "ltype": "SAME",
                                "document": {
                                    "doctype": "Standard",
                                    "name": "ASVS",
                                    "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
                                    "subsection": "3.1.1",
                                    "version": "0.0.0",
                                },
                            }
                        ],
                        "name": "CREname",
                        "tags": ["CREt1", "CREt2"],
                    },
                },
                {
                    "ltype": "SAME",
                    "document": {
                        "doctype": "Standard",
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
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
        }
        self.maxDiff = None
        self.assertDictEqual(standard.todict(), standard_output)
        self.assertDictEqual(nested.todict(), nested_output)
        self.assertDictEqual(cre.todict(), cre_output)
        self.assertDictEqual(group.todict(), group_output)

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

    def test_doc_equality(self) -> None:
        d1 = defs.Code(
            name="c1",
            description="d1",
            tags=["t1", "t2", "t3"],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/c1",
        )
        self.assertEqual(d1, copy.deepcopy(d1))  # happy path
        self.assertNotEqual(
            d1,
            dacite.from_dict(
                data_class=defs.Tool,
                data=copy.deepcopy(d1).todict(),
                config=Config(cast=[defs.ToolTypes, defs.Credoctypes]),
            ),
        )  # happy path

        c = []
        for v in vars(
            d1
        ).keys():  # create a list of standards  they all differ from s1 on one attribute
            if v == "doctype":
                continue
            code = copy.deepcopy(d1)
            vars(code)[v] = f"{vars(d1)[v]}_a"
            c.append(code)
        for cod in c:
            self.assertNotEqual(cod, d1)

        s2 = defs.Standard(
            name="s2",
            section="s2.2",
            subsection="2.2",
            tags=["t1", "t2", "t3"],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/s2",
            version="v2",
        )
        s1_with_link = copy.deepcopy(d1).add_link(defs.Link(document=s2))
        self.assertNotEqual(s1_with_link, d1)

        # assert recursive link equality works
        s1_with_link.links[0].document.add_link(defs.Link(document=c[0]))
        self.assertEquals(s1_with_link, copy.deepcopy(s1_with_link))
        s1_with_link_copy = copy.deepcopy(s1_with_link)
        s1_with_link_copy.links[0].document.links[0].document.add_link(
            defs.Link(document=c[1])
        )
        self.assertFalse(s1_with_link.__eq__(s1_with_link_copy))

    def test_standards_equality(self) -> None:
        s1 = defs.Standard(
            name="s1",
            section="s1.1",
            subsection="1.1",
            tags=["t1", "t2", "t3", ""],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/s1",
            version="v1",
        )
        self.assertEqual(s1, copy.deepcopy(s1))  # happy path
        self.assertNotEqual(
            s1,
            dacite.from_dict(
                data_class=defs.Tool,
                data=copy.deepcopy(s1).todict(),
                config=Config(cast=[defs.Credoctypes]),
            ),
        )  # happy path
        s = []
        for v in vars(
            s1
        ).keys():  # create a list of standards  they all differ from s1 on one attribute
            if v == "doctype":
                continue
            stand = copy.deepcopy(s1)
            vars(stand)[v] = f"{vars(s1)[v]}_a"
            s.append(stand)
        for stand in s:
            self.assertNotEqual(stand, s1)

        s2 = defs.Standard(
            name="s2",
            section="s2.2",
            subsection="2.2",
            tags=["t1", "t2", "t3"],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/s2",
            version="v2",
        )
        s1_with_link = copy.deepcopy(s1).add_link(defs.Link(document=s2))
        self.assertNotEqual(s1_with_link, s1)

        # assert recursive link equality works
        s1_with_link.links[0].document.add_link(defs.Link(document=s[0]))
        self.assertEquals(s1_with_link, copy.deepcopy(s1_with_link))
        s1_with_link_copy = copy.deepcopy(s1_with_link)
        s1_with_link_copy.links[0].document.links[0].document.add_link(
            defs.Link(document=s[1])
        )
        self.assertFalse(s1_with_link.__eq__(s1_with_link_copy))

    def test_add_link(self) -> None:
        tool = defs.Tool(name="mctoolface")
        tool2 = defs.Tool(name="mctoolface2")
        lnk = defs.Link(document=tool2, ltype=defs.LinkTypes.Same)
        actual = copy.deepcopy(tool).add_link(defs.Link(document=tool2))
        tool.links = [lnk]
        self.assertEqual(actual, tool)

        with self.assertRaises(ValueError):
            tool.add_link(link=tool2)  # type: ignore # this is on purpose

    def test_link_equality(self) -> None:
        l0 = defs.Link(
            document=defs.Code(name="foo"),
            ltype=defs.LinkTypes.LinkedTo,
            tags=["t1", "t2"],
        )
        l1 = defs.Link(
            document=defs.Code(name="foo"),
            ltype=defs.LinkTypes.LinkedTo,
            tags=["t1", "t2"],
        )
        self.assertEqual(l0, l1)

        l3 = defs.Link(
            document=defs.Tool(name="foo"),
            ltype=defs.LinkTypes.LinkedTo,
            tags=["t1", "t2"],
        )
        self.assertNotEqual(l0, l3)

        l4 = defs.Link(
            document=defs.Tool(name="Bar"),
            ltype=defs.LinkTypes.LinkedTo,
            tags=["t1", "t2"],
        )
        self.assertNotEqual(l0, l4)

        l5 = defs.Link(
            document=defs.Tool(name="Bar"),
            ltype=defs.LinkTypes.LinkedTo,
            tags=["t1", "t3"],
        )
        self.assertNotEqual(l0, l5)

    def test_link_todict(self) -> None:
        tool = defs.Code(name="Code")
        link = defs.Link(
            ltype=defs.LinkTypes.Contains, document=tool, tags=["1", "2", "3", ""]
        )

        expected = {
            "document": {"doctype": "Code", "name": "Code"},
            "tags": ["1", "2", "3"],
            "ltype": "Contains",
        }
        expected_ignore_empty = {
            "document": {"doctype": "Code", "name": "Code"},
            "ltype": "Contains",
        }

        self.assertDictEqual(link.todict(), expected)

        link.tags = ["", ""]
        self.assertDictEqual(link.todict(), expected_ignore_empty)
        with self.assertRaises(ValueError):
            link.document = None  # type: ignore #this is on purpose
            link.todict()

    def test_tool_todict(self) -> None:
        t0 = defs.Tool(name="toolmctoolface", tooltype=defs.ToolTypes.Offensive)
        expected = {
            "doctype": "Tool",
            "name": "toolmctoolface",
            "tooltype": "Offensive",
        }
        self.assertDictEqual(t0.todict(), expected)
        expected["toolType"] = "Defensive"
        self.assertNotEqual(expected, t0.todict())


if __name__ == "__main__":
    unittest.main()
