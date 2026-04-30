import unittest

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import (
    owasp_kubernetes_top10_2022,
)


class TestOwaspKubernetesTop10_2022Parser(unittest.TestCase):
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
            ("233-748", "Configuration hardening"),
            ("486-813", "Configuration"),
            ("053-751", "Force build pipeline to check outdated/insecure components"),
        ]:
            self.collection.add_cre(defs.CRE(id=cre_id, name=name, description=""))

        result = owasp_kubernetes_top10_2022.OwaspKubernetesTop10_2022().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP Kubernetes Top Ten 2022"]
        self.assertEqual(10, len(entries))
        self.assertEqual("K01", entries[0].sectionID)
        self.assertEqual("Insecure Workload Configurations", entries[0].section)
        self.assertEqual(
            ["233-748", "486-813"], [l.document.id for l in entries[0].links]
        )
        self.assertEqual("K10", entries[-1].sectionID)
        self.assertEqual(["053-751"], [l.document.id for l in entries[-1].links])
