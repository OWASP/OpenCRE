import unittest
from datetime import datetime

from application.utils.harvester.artifact_registry import ArtifactRegistry
from application.utils.harvester.document_deduplicator import (
    DocumentDeduplicator,
)
from application.utils.harvester.models import (
    DeduplicationStatus,
    Document,
    Locator,
    SourceInfo,
)


class DocumentDeduplicatorTests(unittest.TestCase):
    def create_document(self, text: str) -> Document:
        return Document(
            schema_version="0.2.0",
            artifact_id="art:test:file.md",
            pipeline_run_id="run1",
            text=text,
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha="abc123",
                committed_at=datetime.now(),
            ),
            locator=Locator(
                kind="repo_path",
                id="file.md",
                path="file.md",
            ),
            heading_structure=[],
            span=None,
        )

    def test_new_document(self):
        registry = ArtifactRegistry()

        deduplicator = DocumentDeduplicator(registry)
        result = deduplicator.process(self.create_document("hello"))
        self.assertEqual(result, DeduplicationStatus.NEW)

    def test_unchanged_document_refreshes_commit_metadata(self) -> None:
        registry = ArtifactRegistry()
        deduplicator = DocumentDeduplicator(registry)
        first = self.create_document("hello")
        first.source.commit_sha = "aaa111"
        deduplicator.process(first)

        second = self.create_document("hello")
        second.source.commit_sha = "bbb222"
        second.pipeline_run_id = "run2"
        result = deduplicator.process(second)
        self.assertEqual(result, DeduplicationStatus.UNCHANGED)
        stored = registry.get(second.artifact_id)
        assert stored is not None
        self.assertEqual(stored.last_commit_sha, "bbb222")
        self.assertEqual(stored.last_pipeline_run, "run2")

    def test_updated_document(self):
        registry = ArtifactRegistry()

        deduplicator = DocumentDeduplicator(registry)

        deduplicator.process(self.create_document("hello"))

        result = deduplicator.process(
            self.create_document("changed"),
        )

        self.assertEqual(result, DeduplicationStatus.UPDATED)


if __name__ == "__main__":
    unittest.main()
