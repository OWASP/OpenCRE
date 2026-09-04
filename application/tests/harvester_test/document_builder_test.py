import unittest
from datetime import datetime

from application.utils.harvester.document_builder import (
    DocumentBuilder,
)
from application.utils.harvester.models import (
    DiffBlock,
)


class DocumentBuilderTests(unittest.TestCase):
    def test_build_document(self):
        block = DiffBlock(
            file_path="README.md",
            repository="OWASP/ASVS",
            commit_sha="abc123",
            committed_at=datetime.now(),
            added_lines=["Hello"],
        )

        document = DocumentBuilder().build(
            block,
            "# Title\n\nHello",
            pipeline_run_id="20260714T120000Z",
        )

        self.assertEqual(
            document.schema_version,
            "0.2.0",
        )

        self.assertEqual(
            document.artifact_id,
            "art:OWASP/ASVS:README.md",
        )

        self.assertEqual(
            document.pipeline_run_id,
            "20260714T120000Z",
        )

        self.assertEqual(
            document.text,
            "# Title\n\nHello",
        )

        self.assertEqual(
            document.source.repository,
            "OWASP/ASVS",
        )

        self.assertEqual(
            document.locator.path,
            "README.md",
        )

        self.assertEqual(
            len(document.heading_structure),
            1,
        )


if __name__ == "__main__":
    unittest.main()
