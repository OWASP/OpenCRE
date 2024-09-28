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
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
            version="0.0.0",
        )
        standard_output = {
            "id": "ASVS:SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING:3.1.1:0.0.0",
            "doctype": "Standard",
            "name": "ASVS",
            "section": "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            "subsection": "3.1.1",
            "version": "0.0.0",
        }

        cre = defs.CRE(
            id="100-100",
            description="CREdesc",
            name="CREname",
            links=[defs.Link(document=standard, ltype=defs.LinkTypes.LinkedTo)],
            tags=["CREt1", "CREt2"],
        )
        cre_output = {
            "description": "CREdesc",
            "doctype": defs.Credoctypes.CRE.value,
            "id": "100-100",
            "links": [
                {
                    "ltype": defs.LinkTypes.LinkedTo.value,
                    "document": {
                        "id": "ASVS:SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING:3.1.1:0.0.0",
                        "doctype": defs.Credoctypes.Standard.value,
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
            name="Standard",
            section="StandardSection",
            subsection="3.1.1",
        )
        group = defs.CRE(
            id="500-500",
            description="desc",
            name="name",
            links=[
                defs.Link(document=cre, ltype=defs.LinkTypes.Related),
                defs.Link(document=standard2, ltype=defs.LinkTypes.LinkedTo),
            ],
            tags=["tag1", "t2"],
        )
        group_output = {
            "description": "desc",
            "doctype": "CRE",
            "id": "500-500",
            "links": [
                {
                    "ltype": defs.LinkTypes.Related.value,
                    "document": {
                        "description": "CREdesc",
                        "doctype": defs.Credoctypes.CRE.value,
                        "id": "100-100",
                        "links": [
                            {
                                "ltype": defs.LinkTypes.LinkedTo.value,
                                "document": {
                                    "id": "ASVS:SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING:3.1.1:0.0.0",
                                    "doctype": defs.Credoctypes.Standard.value,
                                    "name": "ASVS",
                                    "section": (
                                        "SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING"
                                    ),
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
                    "ltype": defs.LinkTypes.LinkedTo.value,
                    "document": {
                        "id": "Standard:StandardSection:3.1.1",
                        "doctype": defs.Credoctypes.Standard.value,
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
            name="ASVS",
            section="SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING",
            subsection="3.1.1",
        )
        nested_output = {
            "id": "ASVS:SESSION-MGT-TOKEN-DIRECTIVES-DISCRETE-HANDLING:3.1.1",
            "doctype": defs.Credoctypes.Standard.value,
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
        d1 = defs.Standard(
            name="c1",
            embeddings=[0.1, 0.2],
            embeddings_text="some text",
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
            if v == "embeddings":
                vars(code)[v] = [0.001]
                c.append(code)
            elif v == "links":
                code.links = [
                    defs.Link(
                        document=defs.CRE(id="123-123", name="asdf"),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                ]
                c.append(code)
            elif v == "tags":
                vars(code)[v] = [tag + "_a" for tag in d1.tags]
                c.append(code)
            elif v == "metadata":
                code.metadata = {}
                for k, v in d1.metadata:
                    code.metadata[k + "_a"] = v + "_a"
                c.append(code)
            else:
                vars(code)[v] = f"{vars(d1)[v]}_a"
                c.append(code)

        for cod in c:
            self.assertNotEqual(cod.todict(), d1.todict())

        s2 = defs.Standard(
            name="s2",
            section="s2.2",
            subsection="2.2",
            tags=["t1", "t2", "t3"],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/s2",
            version="v2",
        )
        s1_with_link = copy.deepcopy(d1).add_link(
            defs.Link(document=s2, ltype=defs.LinkTypes.LinkedTo)
        )
        self.assertNotEqual(s1_with_link, d1)

    def test_standards_equality(self) -> None:
        s1 = defs.Standard(
            name="s1",
            section="s1.1",
            subsection="1.1",
            embeddings=[0.1],
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
        s = {}
        for v in vars(s1).keys():
            # create a list of standards that all differ from s1 on one attribute
            if v == "doctype":
                continue
            code = copy.deepcopy(s1)
            if v == "embeddings":
                vars(code)[v] = [0.001]
                s["embeddings"] = code
            elif v == "links":
                code.links = [
                    defs.Link(
                        document=defs.CRE(id="123-123", name="asdf"),
                        ltype=defs.LinkTypes.LinkedTo,
                    )
                ]
                s["links"] = code
            elif v == "tags":
                vars(code)[v] = [tag + "_a" for tag in s1.tags]
                s["tags"] = code
            elif v == "metadata":
                code.metadata = {}
                for k, v in s1.metadata:
                    code.metadata[k + "_a"] = v + "_a"
                s["metadata"] = code
            else:
                vars(code)[v] = f"{vars(s1)[v]}_a"
                s[v] = code

        for attribute, stand in s.items():
            self.assertNotEqual(
                stand,
                s1,
                f"stand and s1 are the same but they should have different {attribute}",
            )

        s2 = defs.Standard(
            name="s2",
            section="s2.2",
            subsection="2.2",
            tags=["t1", "t2", "t3"],
            metadata={"m1": "m1.1", "m2": "m2.2"},
            hyperlink="https://example.com/s2",
            version="v2",
        )
        s1_with_link = copy.deepcopy(s1).add_link(
            defs.Link(document=s2, ltype=defs.LinkTypes.LinkedTo)
        )
        self.assertNotEqual(s1_with_link, s1)

    def test_add_link(self) -> None:
        tool = defs.Tool(name="mctoolface")
        tool2 = defs.Tool(name="mctoolface2")
        lnk = defs.Link(document=tool2, ltype=defs.LinkTypes.LinkedTo)
        actual = copy.deepcopy(tool).add_link(
            defs.Link(document=tool2, ltype=defs.LinkTypes.LinkedTo)
        )
        tool.links = [lnk]
        self.assertDictEqual(actual.todict(), tool.todict())

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
        t0 = defs.Tool(
            name="toolmctoolface",
            tooltype=defs.ToolTypes.Offensive,
            sectionID="15",
            section="Rule 15 Title",
        )
        expected = {
            "doctype": "Tool",
            "name": "toolmctoolface",
            "tooltype": "Offensive",
            "sectionID": "15",
            "section": "Rule 15 Title",
            "id": "toolmctoolface:15:Rule 15 Title",
        }
        self.assertDictEqual(t0.todict(), expected)
        expected["toolType"] = "Defensive"
        self.assertNotEqual(expected, t0.todict())


if __name__ == "__main__":
    unittest.main()
