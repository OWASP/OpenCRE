from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils import mapping_fixtures
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
        # Seed the AI-topic hub CREs from the LLM mapping fixture (not classic web CREs).
        gold = mapping_fixtures.load_owasp_mapping_fixture("owasp_llm_top10_2025")
        seeded: set[str] = set()
        for entry in gold:
            for cre_id in entry["cre_ids"]:
                if cre_id in seeded:
                    continue
                self.collection.add_cre(
                    defs.CRE(id=cre_id, name=f"CRE {cre_id}", description="")
                )
                seeded.add(cre_id)

        result = owasp_llm_top10_2025.OwaspLlmTop10_2025().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP Top 10 for LLM and Gen AI Apps 2025"]
        self.assertEqual(10, len(entries))
        self.assertEqual("LLM01", entries[0].sectionID)
        self.assertEqual("Prompt Injection", entries[0].section)
        self.assertEqual(
            ["012-625", "686-110"],
            [link.document.id for link in entries[0].links],
        )
        self.assertEqual(
            ["044-202", "780-757"],
            [link.document.id for link in entries[4].links],
        )
        self.assertEqual("LLM10", entries[-1].sectionID)
        self.assertEqual(["230-318"], [link.document.id for link in entries[-1].links])
