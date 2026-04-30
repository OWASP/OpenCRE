import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import owasp_api_top10_2023


class TestOwaspApiTop10_2023Parser(unittest.TestCase):
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
            ("304-667", "Protect API against unauthorized access/modification (IDOR)"),
            ("724-770", "Technical application access control"),
            ("715-223", "Ensure trusted origin of third party resources"),
        ]:
            self.collection.add_cre(defs.CRE(id=cre_id, name=name, description=""))

        result = owasp_api_top10_2023.OwaspApiTop10_2023().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP API Security Top 10 2023"]
        self.assertEqual(10, len(entries))
        self.assertEqual("API1", entries[0].sectionID)
        self.assertEqual("Broken Object Level Authorization", entries[0].section)
        self.assertEqual(
            ["304-667", "724-770"], [l.document.id for l in entries[0].links]
        )
        self.assertEqual("API10", entries[-1].sectionID)
        self.assertEqual(["715-223"], [l.document.id for l in entries[-1].links])
