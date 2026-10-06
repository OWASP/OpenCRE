"""Event repos are harvested through the event-page parser."""

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
from application.utils.harvester.schemas import HARVESTABLE_KINDS

HEAD = "abc1234def5678"
FIXTURE = Path(__file__).parent / "fixtures" / "event_index.md.txt"

REPOS_YAML = """
repositories:
  - id: owasp-www-event-demo
    kind: event
    enabled: true
    type: github
    owner: OWASP
    repo: www-event-demo
    branch: main
    paths: {include: ["index.md"]}
    chunking: {strategy: markdown_heading, max_tokens: 1000}
    polling: {mode: full, interval_minutes: 1440}
"""


def _client(files):
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def sync(self) -> None:
            pass

        def get_current_commit_sha(self) -> str:
            return HEAD

        def get_file_at_commit(self, sha: str, path: str) -> str:
            return files[path]

        def get_local_path(self) -> Path:
            return Path("/nonexistent")

    return FakeClient


class HarvestEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.tmp = tempfile.TemporaryDirectory()
        self.yaml = Path(self.tmp.name) / "repos.yaml"
        self.yaml.write_text(REPOS_YAML)

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()
        self.tmp.cleanup()

    def _run(self, files):
        patches = [
            patch.object(harvest_pipeline, "GitRepositoryClient", _client(files)),
            patch.object(
                harvest_pipeline.ChangeDetector,
                "get_files_at_commit",
                lambda self, sha: list(files),
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
        return harvest_pipeline.run_harvester(
            sqla.session,
            "run-1",
            repos_yaml=self.yaml,
            sync_repos=False,
            kinds=HARVESTABLE_KINDS,
        )

    def _texts(self):
        return [row.payload["text"] for row in sqla.session.query(db.HarvestInput)]

    def test_events_are_harvestable(self) -> None:
        self.assertIn("event", HARVESTABLE_KINDS)

    def test_event_page_is_parsed_before_chunking(self) -> None:
        summary = self._run({"index.md": FIXTURE.read_text(encoding="utf-8")})
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.repositories, 1)
        self.assertGreater(summary.chunks_written, 0)
        joined = "\n".join(self._texts())
        self.assertIn("Summer of Security 2020", joined)
        self.assertIn("2020-06-23", joined)
        self.assertIn("threat modeling", joined)
        for noise in ("schema.org", "ld+json", "{%", "{{", "layout: event"):
            self.assertNotIn(noise, joined)

    def test_page_with_no_content_is_skipped_and_checkpoint_still_advances(
        self,
    ) -> None:
        from application.utils.harvester.checkpoint_store import CheckpointStore

        summary = self._run(
            {"index.md": "---\nlayout: event\n---\n{% include x.md %}\n"}
        )
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.chunks_written, 0)
        self.assertEqual(
            CheckpointStore(session=sqla.session)
            .load("owasp-www-event-demo")
            .last_processed_commit,
            HEAD,
        )


if __name__ == "__main__":
    unittest.main()
