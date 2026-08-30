import unittest
from datetime import datetime
from unittest.mock import Mock

from application.utils.harvester.artifact_registry import ArtifactRegistry
from application.utils.harvester.document_deduplicator import DocumentDeduplicator
from application.utils.harvester.incremental_pipeline import IncrementalPipeline
from application.utils.harvester.models import Document, Locator, SourceInfo


class IncrementalPipelineTests(unittest.TestCase):
    def make_document(self, text: str, commit_sha: str = "abc1234") -> Document:
        return Document(
            schema_version="0.2.0",
            artifact_id="art:OWASP/ASVS:file.md",
            pipeline_run_id="run1",
            text=text,
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha=commit_sha,
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

    def test_only_new_and_updated_are_emitted(self) -> None:
        registry = ArtifactRegistry()
        dedup = DocumentDeduplicator(registry)
        store = Mock()
        pipeline = IncrementalPipeline(
            deduplicator=dedup,
            checkpoint_store=store,
            provider="github",
            owner="OWASP",
            repository_name="ASVS",
            branch="master",
            repository_id="owasp-asvs",
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
            last_processed_commit="abc1234",
        )
        self.assertEqual(len(emitted), 2)
        store.save.assert_called_once()
        saved = store.save.call_args[0][0]
        self.assertEqual(saved.last_processed_commit, "abc1234")

    def test_rejects_empty_checkpoint_commit(self) -> None:
        pipeline = IncrementalPipeline(
            checkpoint_store=Mock(),
            owner="OWASP",
            repository_name="ASVS",
            repository_id="owasp-asvs",
        )
        with self.assertRaises(ValueError):
            pipeline.process(
                "OWASP/ASVS",
                "run1",
                [self.make_document("hello")],
                last_processed_commit="   ",
            )


if __name__ == "__main__":
    unittest.main()
