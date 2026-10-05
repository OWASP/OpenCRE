"""Checkpoints advance only after chunks are staged; bad documents are isolated."""

from cre_logging import get_logger

logger = get_logger(__name__)

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.utils.harvester import pipeline as harvest_pipeline
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline

HEAD = "abc1234def5678"

REPOS_YAML = """
repositories:
  - id: owasp-demo
    kind: standard
    enabled: true
    type: github
    owner: OWASP
    repo: demo
    branch: main
    paths: {include: ["**/*.md"]}
    chunking: {strategy: fixed_size, max_tokens: 200, overlap_tokens: 0}
    polling: {mode: incremental, interval_minutes: 60}
"""

FILES = {
    "good.md": "# Good\n\nThis document chunks fine and has enough words.\n",
    "bad.md": "# Bad\n\nThis document makes the chunk pipeline raise.\n",
}


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def sync(self) -> None:
        pass

    def get_current_commit_sha(self) -> str:
        return HEAD

    def get_file_at_commit(self, sha: str, path: str) -> str:
        return FILES[path]

    def get_local_path(self) -> Path:
        return Path("/nonexistent")


class HarvestCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.tmp = tempfile.TemporaryDirectory()
        self.yaml = Path(self.tmp.name) / "repos.yaml"
        self.yaml.write_text(REPOS_YAML)
        patches = [
            patch.object(harvest_pipeline, "GitRepositoryClient", FakeClient),
            patch.object(
                harvest_pipeline.ChangeDetector,
                "get_files_at_commit",
                lambda self, sha: list(FILES),
            ),
            patch.object(
                harvest_pipeline,
                "_commit_timestamp",
                lambda client, sha: datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()
        self.tmp.cleanup()

    def _run(self, **kwargs):
        return harvest_pipeline.run_harvester(
            sqla.session, "run-1", repos_yaml=self.yaml, sync_repos=False, **kwargs
        )

    def _checkpoint(self):
        return CheckpointStore(session=sqla.session).load("owasp-demo")

    def test_checkpoint_saved_after_successful_write(self) -> None:
        summary = self._run()
        self.assertEqual(summary.errors, 0)
        self.assertGreater(summary.chunks_written, 0)
        self.assertEqual(self._checkpoint().last_processed_commit, HEAD)

    def test_checkpoint_not_saved_when_write_fails(self) -> None:
        with patch.object(
            harvest_pipeline, "write_harvest_input", side_effect=RuntimeError("db down")
        ):
            summary = self._run()
        self.assertEqual(summary.errors, 1)
        self.assertIsNone(self._checkpoint())

    def test_dry_run_leaves_no_checkpoint(self) -> None:
        summary = self._run(dry_run=True)
        self.assertGreater(summary.chunks_written, 0)
        self.assertIsNone(self._checkpoint())

    def test_one_bad_document_does_not_discard_the_rest(self) -> None:
        real_chunk = DocumentChunkPipeline.chunk

        def flaky(self, document):
            if document.locator.path == "bad.md":
                raise ValueError("boom")
            return real_chunk(self, document)

        with patch.object(DocumentChunkPipeline, "chunk", flaky):
            summary = self._run()
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.status, "degraded")
        self.assertGreater(summary.chunks_written, 0)
        self.assertEqual(self._checkpoint().last_processed_commit, HEAD)
        paths = {
            row.payload["artifact_id"] for row in sqla.session.query(db.HarvestInput)
        }
        self.assertTrue(all("good.md" in p for p in paths), paths)


if __name__ == "__main__":
    unittest.main()
