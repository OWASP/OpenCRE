import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import owasp_aisvs


class TestOwaspAisvsParser(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def test_parse(self) -> None:
        for cre_id, name in [
            ("227-045", "Identify sensitive data and subject it to a policy"),
            (
                "307-507",
                "Allow only trusted sources both build time and runtime; therefore perform integrity checks on all resources and code",
            ),
            (
                "162-655",
                "Documentation of all components' business or security function",
            ),
        ]:
            self.collection.add_cre(defs.CRE(id=cre_id, name=name, description=""))

        result = owasp_aisvs.OwaspAisvs().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP AI Security Verification Standard (AISVS)"]
        self.assertEqual(14, len(entries))
        self.assertEqual("AISVS1", entries[0].sectionID)
        self.assertEqual(
            "Training Data Governance & Bias Management", entries[0].section
        )
        self.assertEqual(
            "https://github.com/OWASP/AISVS/tree/main/1.0/en/0x10-C01-Training-Data-Governance.md",
            entries[0].hyperlink,
        )
        self.assertEqual(
            ["227-045", "307-507"], [l.document.id for l in entries[0].links]
        )
        self.assertEqual("AISVS14", entries[-1].sectionID)
        self.assertEqual(
            "Human Oversight, Accountability & Governance", entries[-1].section
        )
        self.assertEqual(
            "https://github.com/OWASP/AISVS/tree/main/1.0/en/0x10-C14-Human-Oversight.md",
            entries[-1].hyperlink,
        )
        self.assertEqual(["162-655"], [l.document.id for l in entries[-1].links])
