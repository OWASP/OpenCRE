from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
import tempfile
from unittest.mock import Mock, patch
import os
from application.utils import git

from application.utils.external_project_parsers.parsers import zap_alerts_parser
from application.prompt_client import prompt_client


class TestZAPAlertsParser(unittest.TestCase):
    class Repo:
        working_dir = ""

    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

        self.collection = db.Node_collection()

    @patch.object(git, "clone")
    def test_register_zap_alert_top_10_tags(self, mock_git) -> None:
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

        repo = self.Repo()
        loc = tempfile.mkdtemp()
        path = os.path.join(loc, zap_alerts_parser.ZAP().alerts_path)
        os.makedirs(path)
        repo.working_dir = loc
        mock_git.return_value = repo
        with open(os.path.join(path, "alert0.md"), "w") as mdf:
            mdf.write(alert)

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
        entries = zap_alerts_parser.ZAP().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )
        for name, nodes in entries.results.items():
            self.assertEqual(name, zap_alerts_parser.ZAP().name)
            expected = defs.Tool(
                name="ZAP Rule",
                sectionID="10003",
                section="Vulnerable JS Library",
                doctype=defs.Credoctypes.Tool,
                description="_Unavailable_",
                tags=["10003", "Passive"],
                hyperlink="https://github.com/zaproxy/zap-extensions/blob/main/addOns/retire/src/main/java/org/zaproxy/addon/retire/RetireScanRule.java",
                tooltype=defs.ToolTypes.Offensive,
                links=[
                    defs.Link(
                        document=db.CREfromDB(cre), ltype=defs.LinkTypes.LinkedTo
                    ),
                    defs.Link(
                        document=db.CREfromDB(cre2), ltype=defs.LinkTypes.LinkedTo
                    ),
                    defs.Link(
                        document=db.CREfromDB(cre3), ltype=defs.LinkTypes.LinkedTo
                    ),
                ],
            )

            self.maxDiff = None
            self.assertEqual(len(nodes), 1)
            self.assertCountEqual(expected.todict(), nodes[0].todict())
            for node in nodes:
                self.assertNotIn(
                    cre3.external_id, [link.document.id for link in node.links]
                )
                self.assertIn(
                    cre.external_id, [link.document.id for link in node.links]
                )
                self.assertIn(
                    cre2.external_id, [link.document.id for link in node.links]
                )

    @patch.object(git, "clone")
    def test_register_zap_alert_cwe(self, mock_git) -> None:
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

        repo = self.Repo()
        loc = tempfile.mkdtemp()
        path = os.path.join(loc, zap_alerts_parser.ZAP().alerts_path)
        os.makedirs(path)
        repo.working_dir = loc
        mock_git.return_value = repo
        with open(os.path.join(path, "alert0.md"), "w") as mdf:
            mdf.write(alert)

        dbcre0 = self.collection.add_cre(defs.CRE(name="foo", id="111-110"))
        dbcre1 = self.collection.add_cre(defs.CRE(name="foo1", id="111-111"))
        dbcwe = self.collection.add_node(defs.Standard(name="CWE", sectionID="1021"))
        self.collection.add_link(cre=dbcre0, node=dbcwe)
        self.collection.add_link(cre=dbcre1, node=dbcwe)

        entries = zap_alerts_parser.ZAP().parse(
            cache=self.collection, ph=prompt_client.PromptHandler(self.collection)
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
            links=[
                defs.Link(document=db.CREfromDB(dbcre0), ltype=defs.LinkTypes.LinkedTo),
                defs.Link(document=db.CREfromDB(dbcre1), ltype=defs.LinkTypes.LinkedTo),
            ],
        )
        self.maxDiff = None
        for name, nodes in entries.results.items():
            self.assertEqual(name, zap_alerts_parser.ZAP().name)
            self.assertEqual(len(nodes), 1)
            self.assertCountEqual(expected.todict(), nodes[0].todict())
