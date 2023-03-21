from cmath import exp
from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
import tempfile
import os

from application.utils.external_project_parsers import zap_alerts_parser


class TestZAPAlertsParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        sqla.create_all(app=self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.collection = db.Node_collection()

    def test_register_zap_alert_top_10_tags(self) -> None:
        alert = """
      ---
      title: "Vulnerable JS Library"
      alertid: 10003
      alertindex: 1000300
      alerttype: "Passive"
      alertcount: 1
      status: release
      type: alert
      solution: "_Unavailable_"
      alerttags: 
        - OWASP_2017_A09
        - OWASP_2021_A06
      code: https://github.com/zaproxy/zap-extensions/blob/main/addOns/retire/src/main/java/org/zaproxy/addon/retire/RetireScanRule.java
      linktext: org/zaproxy/addon/retire/RetireScanRule.java
      ---
      _Unavailable_
      """

        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        repo.working_dir = loc
        top10s = [
            self.collection.add_node(
                defs.Standard(
                    name="Top10 2015", section="A9_Wrong Year", subsection="wrong year"
                )
            ),
            self.collection.add_node(
                defs.Standard(
                    name="Top10 2021",
                    section="A6_Security_Misconfiguration",
                    subsection="something",
                )
            ),
            self.collection.add_node(
                defs.Standard(
                    name="Top10 2017",
                    section="A9 Using Components With Known Vulnerabilities",
                )
            ),
            self.collection.add_node(
                defs.Standard(name="Top10 2021", section="A0 Something Irrelevant")
            ),
        ]
        cre = self.collection.add_cre(defs.CRE(name="foo", id="000-000"))
        [
            self.collection.add_link(cre, top10)
            for top10 in top10s
            if top10.subsection == "something"
        ]

        cre2 = self.collection.add_cre(defs.CRE(name="bar", id="000-001"))
        [
            self.collection.add_link(cre2, top10)
            for top10 in top10s
            if top10.subsection == ""
        ]

        cre3 = self.collection.add_cre(defs.CRE(name="foobar", id="000-003"))
        [
            self.collection.add_link(cre, top10)
            for top10 in top10s
            if top10.subsection == "wrong year"
        ]

        with open(os.path.join(loc, "alert0.md"), "w") as mdf:
            mdf.write(alert)
        zap_alerts_parser.register_alerts(
            cache=self.collection, repo=repo, alerts_path=""
        )

        expected = defs.Tool(
            name="ZAP Rule",
            sectionID="10003",
            section="Vulnerable JS Library",
            doctype=defs.Credoctypes.Tool,
            description="_Unavailable_",
            tags=["10003", "Passive"],
            hyperlink="https://github.com/zaproxy/zap-extensions/blob/main/addOns/retire/src/main/java/org/zaproxy/addon/retire/RetireScanRule.java",
            tooltype=defs.ToolTypes.Offensive,
        )

        self.maxDiff = None
        node = db.nodeFromDB(
            self.collection.session.query(db.Node)
            .filter(db.Node.name == expected.name)
            .first()
        )
        self.assertCountEqual(expected.todict(), node.todict())

        node = self.collection.get_nodes(name=expected.name, ntype=expected.doctype)[0]
        self.assertNotIn(cre3.external_id, [link.document.id for link in node.links])
        self.assertIn(cre.external_id, [link.document.id for link in node.links])
        self.assertIn(cre2.external_id, [link.document.id for link in node.links])

    def test_register_zap_alert_cwe(self) -> None:
        class Repo:
            working_dir = ""

        repo = Repo()
        loc = tempfile.mkdtemp()
        repo.working_dir = loc

        cre = self.collection.add_cre(defs.CRE(name="foo", id="111-111"))
        cwe = self.collection.add_node(defs.Standard(name="CWE", sectionID="1021"))
        self.collection.add_link(cre=cre, node=cwe)

        with open(os.path.join(loc, "alert0.md"), "w") as mdf:
            mdf.write(alert)
        zap_alerts_parser.register_alerts(
            cache=self.collection, repo=repo, alerts_path=""
        )

        expected = defs.Tool(
            name="ZAP Rule",
            section="Multiple X-Frame-Options Header Entries",
            sectionID="10020-2",
            doctype=defs.Credoctypes.Tool,
            description="Ensure only a single X-Frame-Options header is present in the response.",
            tags=["10020-2", "Passive"],
            hyperlink="https://github.com/zaproxy/zap-extensions/blob/main/addOns/pscanrules/src/main/java/org/zaproxy/zap/extension/pscanrules/AntiClickjackingScanRule.java",
            tooltype=defs.ToolTypes.Offensive,
        )
        self.maxDiff = None
        actual = db.nodeFromDB(
            self.collection.session.query(db.Node)
            .filter(db.Node.name == expected.name)
            .filter(db.Node.section_id == expected.sectionID)
            .first()
        )
        self.assertCountEqual(expected.tags, actual.tags)
        tags_copy = actual.tags
        actual.tags = [""]
        expected.tags = [""]
        self.assertDictEqual(expected.todict(), actual.todict())

        links = self.collection.get_CREs(external_id="111-111")[0].links

        expected.tags = tags_copy
        if links[0].document.hyperlink == expected.hyperlink:
            self.assertDictEqual(expected.todict(), links[0].document.todict())
        else:
            self.assertDictEqual(expected.todict(), links[1].document.todict())


alert = """
---
title: "Multiple X-Frame-Options Header Entries"
alertid: 10020-2
alertindex: 1002002
alerttype: "Passive"
alertcount: 4
status: release
type: alert
risk: Medium
solution: "Ensure only a single X-Frame-Options header is present in the response."
references:
   - https://tools.ietf.org/html/rfc7034
cwe: 1021
wasc: 15
alerttags: 
  - Some_Other_standard_2017_A06
  - Some_Other_standard_2027_A04
  - WSTG-v42-CLNT-09
code: https://github.com/zaproxy/zap-extensions/blob/main/addOns/pscanrules/src/main/java/org/zaproxy/zap/extension/pscanrules/AntiClickjackingScanRule.java
linktext: org/zaproxy/zap/extension/pscanrules/AntiClickjackingScanRule.java
---
X-Frame-Options (XFO) headers were found, a response with multiple XFO header entries may not be predictably treated by all user-agents.
"""
