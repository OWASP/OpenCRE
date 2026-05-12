import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import owasp_llm_top10_2025


class TestOwaspLlmTop10_2025Parser(unittest.TestCase):
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
            ("161-451", "Output encoding and injection prevention"),
            ("064-808", "Encode output context-specifically"),
            ("760-764", "Injection protection"),
            ("623-550", "Denial Of Service protection"),
        ]:
            self.collection.add_cre(defs.CRE(id=cre_id, name=name, description=""))

        result = owasp_llm_top10_2025.OwaspLlmTop10_2025().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP Top 10 for LLM and Gen AI Apps 2025"]
        self.assertEqual(10, len(entries))
        self.assertEqual("LLM01", entries[0].sectionID)
        self.assertEqual("Prompt Injection", entries[0].section)
        self.assertEqual(
            ["161-451", "760-764"], [l.document.id for l in entries[0].links]
        )
        self.assertEqual(["064-808"], [l.document.id for l in entries[4].links])
        self.assertEqual("LLM10", entries[-1].sectionID)
        self.assertEqual(["623-550"], [l.document.id for l in entries[-1].links])
