import unittest
from datetime import datetime

from application.utils.harvester.artifact_registry import ArtifactRegistry
from application.utils.harvester.models import ArtifactRegistryRecord


class ArtifactRegistryTests(unittest.TestCase):
    def test_insert_record(self):
        registry = ArtifactRegistry()

        record = ArtifactRegistryRecord(
            artifact_id="art:test:file.md",
            repository="OWASP/ASVS",
            locator_path="file.md",
            content_hash="abc",
            last_commit_sha="123",
            last_pipeline_run="run1",
            last_processed_at=datetime.now(),
            status="new",
        )

        registry.upsert(record)

        self.assertTrue(registry.exists(record.artifact_id))

    def test_get_record(self):
        registry = ArtifactRegistry()

        record = ArtifactRegistryRecord(
            artifact_id="art:test:file.md",
            repository="OWASP/ASVS",
            locator_path="file.md",
            content_hash="abc",
            last_commit_sha="123",
            last_pipeline_run="run1",
            last_processed_at=datetime.now(),
            status="new",
        )

        registry.upsert(record)

        stored = registry.get(record.artifact_id)
        assert stored is not None

        self.assertEqual(stored.content_hash, "abc")

    def test_update_record(self):
        registry = ArtifactRegistry()

        record = ArtifactRegistryRecord(
            artifact_id="art:test:file.md",
            repository="OWASP/ASVS",
            locator_path="file.md",
            content_hash="abc",
            last_commit_sha="123",
            last_pipeline_run="run1",
            last_processed_at=datetime.now(),
            status="new",
        )

        registry.upsert(record)

        record.content_hash = "xyz"
        record.status = "updated"

        registry.upsert(record)

        stored = registry.get(record.artifact_id)
        assert stored is not None

        self.assertEqual(stored.content_hash, "xyz")
        self.assertEqual(stored.status, "updated")

    def test_all_records(self):
        registry = ArtifactRegistry()

        for i in range(3):
            registry.upsert(
                ArtifactRegistryRecord(
                    artifact_id=f"art:{i}",
                    repository="repo",
                    locator_path=f"{i}.md",
                    content_hash=str(i),
                    last_commit_sha="sha",
                    last_pipeline_run="run",
                    last_processed_at=datetime.now(),
                    status="new",
                )
            )

        self.assertEqual(
            len(registry.all()),
            3,
        )


if __name__ == "__main__":
    unittest.main()
