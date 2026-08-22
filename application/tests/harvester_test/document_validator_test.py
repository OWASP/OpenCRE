import unittest
from datetime import datetime

from application.utils.harvester.document_validator import (
    DocumentValidator,
)
from application.utils.harvester.models import (
    Document,
    HeadingNode,
    Locator,
    SourceInfo,
)


def make_document() -> Document:
    return Document(
        schema_version="0.2.0",
        artifact_id="art:OWASP/ASVS:README.md",
        pipeline_run_id="20260714T120000Z",
        text="# Title",
        source=SourceInfo(
            type="github",
            repository="OWASP/ASVS",
            commit_sha="abc123",
            committed_at=datetime.now(),
        ),
        locator=Locator(
            kind="repo_path",
            id="README.md",
            path="README.md",
        ),
        heading_structure=[
            HeadingNode(
                level=1,
                text="Title",
                start_line=1,
                end_line=1,
            )
        ],
        span=None,
    )


class DocumentValidatorTests(unittest.TestCase):
    def test_valid_document(self):
        validator = DocumentValidator()

        self.assertTrue(validator.validate(make_document()))

    def test_missing_artifact_id(self):
        validator = DocumentValidator()

        document = make_document()
        document.artifact_id = ""

        self.assertFalse(validator.validate(document))

    def test_missing_text(self):
        validator = DocumentValidator()

        document = make_document()
        document.text = ""

        self.assertFalse(validator.validate(document))

    def test_invalid_source_type(self):
        validator = DocumentValidator()

        document = make_document()
        document.source.type = "gitlab"

        self.assertFalse(validator.validate(document))

    def test_non_markdown_document_is_valid(self):
        validator = DocumentValidator()

        document = make_document()
        document.heading_structure = []
        document.text = '{"hello": "world"}'

        self.assertTrue(validator.validate(document))


if __name__ == "__main__":
    unittest.main()
