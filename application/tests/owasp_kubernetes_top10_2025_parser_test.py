import unittest
import tempfile
from pathlib import Path

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.parsers import (
    owasp_kubernetes_top10_2025,
)


class TestOwaspKubernetesTop10_2025Parser(unittest.TestCase):
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
            ("148-420", "Log integrity"),
            ("402-706", "Log relevant"),
            ("843-841", "Log discretely"),
        ]:
            self.collection.add_cre(defs.CRE(id=cre_id, name=name, description=""))

        result = owasp_kubernetes_top10_2025.OwaspKubernetesTop10_2025().parse(
            self.collection, prompt_client.PromptHandler(database=self.collection)
        )

        entries = result.results["OWASP Kubernetes Top Ten 2025 (Draft)"]
        self.assertEqual(10, len(entries))
        self.assertEqual("K01", entries[0].sectionID)
        self.assertEqual("Insecure Workload Configurations", entries[0].section)
        self.assertEqual(
            ["233-748", "486-813"], [l.document.id for l in entries[0].links]
        )
        self.assertEqual("K10", entries[-1].sectionID)
        self.assertEqual(
            ["148-420", "402-706", "843-841"],
            [l.document.id for l in entries[-1].links],
        )

    def test_parse_falls_back_to_2022_mapping_when_2025_links_missing(self) -> None:
        self.collection.add_cre(
            defs.CRE(id="148-420", name="Log integrity", description="")
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            current_file = tmp_path / "k8s_2025.json"
            fallback_file = tmp_path / "k8s_2022.json"
            current_file.write_text(
                """
[
  {
    "section_id": "K10",
    "section": "Inadequate Logging And Monitoring",
    "hyperlink": "https://example.com/k10",
    "cre_ids": ["999-999"],
    "fallback_section_ids": ["K05"]
  }
]
                """.strip(),
                encoding="utf-8",
            )
            fallback_file.write_text(
                """
[
  {
    "section_id": "K05",
    "section": "Inadequate Logging and Monitoring",
    "hyperlink": "https://example.com/k05",
    "cre_ids": ["148-420"]
  }
]
                """.strip(),
                encoding="utf-8",
            )

            parser = owasp_kubernetes_top10_2025.OwaspKubernetesTop10_2025()
            parser.data_file = current_file
            parser.fallback_data_file = fallback_file

            result = parser.parse(
                self.collection,
                prompt_client.PromptHandler(database=self.collection),
            )

        entries = result.results["OWASP Kubernetes Top Ten 2025 (Draft)"]
        self.assertEqual(1, len(entries))
        self.assertEqual(["148-420"], [link.document.id for link in entries[0].links])
