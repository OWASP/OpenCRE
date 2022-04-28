from application.utils import mdutils
from application.defs import cre_defs as defs
from pprint import pprint
import unittest
from application import create_app, sqla  # type: ignore


class TestMdutilsParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()

    def test_cre_to_md(self) -> None:
        standards = [
            defs.Standard(
                name=f"sname",
                section=f"section_{s}",
                hyperlink=f"https://example.com/sname/{s}",
            )
            for s in range(1, 10)
        ]
        standards2 = [
            defs.Standard(
                name=f"sname_other",
                section=f"section_{s}",
                hyperlink=f"https://example.com/sname/{s}",
            )
            for s in range(1, 10)
        ]
        cres = [
            defs.CRE(name=f"cname_{s}", description=f"description_{s}", id=f"000-00{s}")
            for s in range(1, 10)
        ]
        tools = [
            defs.Tool(
                name=f"tname_{s}",
                tooltype=defs.ToolTypes.Training,
                hyperlink=f"https://example.com/tnae/{s}",
            )
            for s in range(1, 10)
        ]

        for i in range(0, 9):
            standards[i].add_link(defs.Link(document=cres[i]))
            if not i % 2:
                standards[i].add_link(defs.Link(document=tools[i]))
            else:
                standards[i].add_link(defs.Link(document=standards2[i]))
        self.maxDiff = None
        self.assertEqual(mdutils.cre_to_md(standards), self.result)

    result = """sname | CRE | tname_1 | sname_other | tname_3 | tname_5 | tname_7 | tname_9
----- | --- | ------- | ----------- | ------- | ------- | ------- | -------
[sname section_1](https://example.com/sname/1) | [000-001 cname_1](https://www.opencre.org/cre/000-001) | [tname_1](https://example.com/tnae/1) |   |   |   |   |  
[sname section_2](https://example.com/sname/2) | [000-002 cname_2](https://www.opencre.org/cre/000-002) |   | [sname_other section_2](https://example.com/sname/2) |   |   |   |  
[sname section_3](https://example.com/sname/3) | [000-003 cname_3](https://www.opencre.org/cre/000-003) |   |   | [tname_3](https://example.com/tnae/3) |   |   |  
[sname section_4](https://example.com/sname/4) | [000-004 cname_4](https://www.opencre.org/cre/000-004) |   | [sname_other section_4](https://example.com/sname/4) |   |   |   |  
[sname section_5](https://example.com/sname/5) | [000-005 cname_5](https://www.opencre.org/cre/000-005) |   |   |   | [tname_5](https://example.com/tnae/5) |   |  
[sname section_6](https://example.com/sname/6) | [000-006 cname_6](https://www.opencre.org/cre/000-006) |   | [sname_other section_6](https://example.com/sname/6) |   |   |   |  
[sname section_7](https://example.com/sname/7) | [000-007 cname_7](https://www.opencre.org/cre/000-007) |   |   |   |   | [tname_7](https://example.com/tnae/7) |  
[sname section_8](https://example.com/sname/8) | [000-008 cname_8](https://www.opencre.org/cre/000-008) |   | [sname_other section_8](https://example.com/sname/8) |   |   |   |  
[sname section_9](https://example.com/sname/9) | [000-009 cname_9](https://www.opencre.org/cre/000-009) |   |   |   |   |   | [tname_9](https://example.com/tnae/9)
"""
