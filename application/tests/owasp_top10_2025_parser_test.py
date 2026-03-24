import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import owasp_top10_2025


class TestOwaspTop10_2025Parser(unittest.TestCase):
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
        self.collection.add_cre(
            defs.CRE(id="177-260", name="Session management", description="")
        )
        self.collection.add_cre(
            defs.CRE(
                id="117-371",
                name="Use a centralized access control mechanism",
                description="",
            )
        )
        self.collection.add_cre(
            defs.CRE(
                id="724-770",
                name="Technical application access control",
                description="",
            )
        )
        self.collection.add_cre(
            defs.CRE(
                id="031-447", name="Whitelist all external (HTTP) input", description=""
            )
        )
        self.collection.add_cre(
            defs.CRE(
                id="064-808", name="Encode output context-specifically", description=""
            )
        )
        self.collection.add_cre(
            defs.CRE(id="760-764", name="Injection protection", description="")
        )
        self.collection.add_cre(
            defs.CRE(id="513-183", name="Error handling", description="")
        )

        result = owasp_top10_2025.OwaspTop10_2025().parse(
            self.collection,
            prompt_client.PromptHandler(database=self.collection),
        )

        entries = result.results["OWASP Top 10 2025"]
        self.assertEqual(10, len(entries))
        self.assertEqual("A01", entries[0].sectionID)
        self.assertEqual("Broken Access Control", entries[0].section)
        self.assertEqual(
            "https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/",
            entries[0].hyperlink,
        )
        self.assertEqual(
            ["117-371", "177-260", "724-770"],
            [link.document.id for link in entries[0].links],
        )
        self.assertEqual(
            ["031-447", "064-808", "760-764"],
            [link.document.id for link in entries[4].links],
        )
        self.assertEqual("A10", entries[-1].sectionID)
        self.assertEqual(["513-183"], [link.document.id for link in entries[-1].links])
