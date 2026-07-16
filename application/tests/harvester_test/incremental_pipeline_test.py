import unittest
from datetime import datetime

from application.utils.harvester.artifact_registry import ArtifactRegistry
from application.utils.harvester.checkpoint_manager import CheckpointManager
from application.utils.harvester.document_deduplicator import (
    DocumentDeduplicator,
)
from application.utils.harvester.incremental_pipeline import (
    IncrementalPipeline,
)
from application.utils.harvester.models import (
    Document,
    Locator,
    SourceInfo,
)


class IncrementalPipelineTests(unittest.TestCase):
    def make_document(self, text: str) -> Document:

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

    def test_only_new_and_updated_are_emitted(self):
        registry = ArtifactRegistry()

        dedup = DocumentDeduplicator(
            registry,
        )

        checkpoints = CheckpointManager()

        pipeline = IncrementalPipeline(
            dedup,
            checkpoints,
        )

        docs = [
            self.make_document("hello"),
            self.make_document("hello"),
            self.make_document("changed"),
        ]

        emitted = pipeline.process(
            "OWASP/ASVS",
            "run1",
            docs,
        )

        self.assertEqual(len(emitted), 2)
        checkpoint = checkpoints.get("OWASP/ASVS")

        assert checkpoint is not None
        self.assertEqual(checkpoint.status, "completed")


if __name__ == "__main__":
    unittest.main()
