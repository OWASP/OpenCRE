"""Real Git and SQLite regressions for first-run repository harvesting."""

import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from application.database.db import HarvesterCheckpoint, HarvestInput
from application.utils.harvester.change_detector import ChangeDetector
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.document_builder import DocumentBuilder
from application.utils.harvester.git_repository_client import GitRepositoryClient
from application.utils.harvester.models import RepositoryCheckpoint
from application.utils.harvester.pipeline import RunSummary, _harvest_repository
from application.utils.harvester.schemas import RepositoryConfig


class FirstHarvestTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture_root = Path(__file__).resolve().parents[3] / "tmp" / "harvester-it"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.tempdir = tempfile.TemporaryDirectory(dir=fixture_root)
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.git("init", "--initial-branch=main", "--object-format=sha1")
        self.client = GitRepositoryClient(
            owner="OWASP", repository="fixture", local_path=self.root
        )
        self.detector = ChangeDetector(self.client)

        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        HarvesterCheckpoint.__table__.create(self.engine)
        HarvestInput.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.store = CheckpointStore(session=self.session)
        self.config = RepositoryConfig.model_validate(
            {
                "id": "owasp-fixture",
                "type": "github",
                "owner": "OWASP",
                "repo": "fixture",
                "branch": "main",
                "paths": {
                    "include": ["docs/**/*.md"],
                    "exclude": ["docs/archive/**"],
                },
                "chunking": {
                    "strategy": "markdown_heading",
                    "max_tokens": 200,
                    "overlap_tokens": 10,
                },
                "polling": {"mode": "incremental", "interval_minutes": 60},
            }
        )

    def git(self, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Test User",
                "-c",
                "user.email=test@example.invalid",
                "-C",
                str(self.root),
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()

    def write_file(self, name: str, text: str = "# Auth\nUse MFA.\n") -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-m", "Fixture snapshot")
        return self.git("rev-parse", "HEAD")

    def harvest(self, run_id: str = "first-run") -> tuple[int, RunSummary]:
        summary = RunSummary(run_id=run_id)
        # Only redirect repository construction to the disposable local clone.
        # Git commands, filters, builders, chunk validation and DB writes are real.
        with patch(
            "application.utils.harvester.pipeline.GitRepositoryClient",
            return_value=self.client,
        ):
            written = _harvest_repository(
                session=self.session,
                repo_cfg=self.config,
                pipeline_run_id=run_id,
                checkpoint_store=self.store,
                builder=DocumentBuilder(),
                dry_run=False,
                sync_repos=False,
                summary=summary,
            )
        return written, summary

    def test_lists_snapshot_paths_without_git_quoting_or_worktree_files(self) -> None:
        paths = [
            "docs/auth.md",
            "docs/nested/café.md",
            "docs/login with spaces.md",
            "docs/tab\tname.md",
            "docs/line\nname.md",
            "docs/carriage\rreturn.md",
        ]
        for path in paths:
            self.write_file(path)
        head = self.commit()
        self.write_file("later.md")
        self.commit()
        self.write_file("untracked.md")

        self.assertEqual(self.detector.get_tracked_files(head), sorted(paths))

    def test_first_harvest_applies_filters_and_writes_documents_and_checkpoint(
        self,
    ) -> None:
        included = {
            "docs/auth.md",
            "docs/nested/café.md",
            "docs/login with spaces.md",
        }
        excluded = {"docs/archive/old.md", "docs/app.js", "README.md"}
        for path in included | excluded:
            self.write_file(path)
        head = self.commit()

        written, summary = self.harvest()

        rows = self.session.query(HarvestInput).all()
        self.assertEqual(written, len(included))
        self.assertEqual({row.payload["locator"]["path"] for row in rows}, included)
        self.assertTrue(all(row.status == "pending" for row in rows))
        self.assertTrue(
            all(row.payload["source"]["commit_sha"] == head for row in rows)
        )
        self.assertEqual(summary.files_seen, len(included | excluded))
        self.assertEqual(summary.files_retained, len(included))
        self.assertEqual(summary.documents_emitted, len(included))
        checkpoint = self.store.load(self.config.id)
        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(checkpoint.last_processed_commit, head)

    def test_empty_committed_repository_saves_checkpoint_without_queue_rows(
        self,
    ) -> None:
        head = self.commit()

        written, summary = self.harvest()

        self.assertEqual(written, 0)
        self.assertEqual(summary.files_seen, 0)
        self.assertEqual(summary.documents_emitted, 0)
        self.assertEqual(self.session.query(HarvestInput).count(), 0)
        checkpoint = self.store.load(self.config.id)
        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(checkpoint.last_processed_commit, head)

    def test_existing_checkpoint_harvests_only_changed_files(self) -> None:
        self.write_file("docs/auth.md")
        self.write_file("docs/unchanged.md")
        base = self.commit()
        self.store.save(
            RepositoryCheckpoint(
                repository_id=self.config.id,
                last_processed_commit=base,
                updated_at=datetime.now(timezone.utc),
                provider="github",
                owner="OWASP",
                repository="fixture",
                branch="main",
            )
        )
        self.write_file("docs/auth.md", "# Auth\nRequire MFA and review sessions.\n")
        self.write_file("docs/new.md")
        head = self.commit()

        written, summary = self.harvest("incremental-run")

        paths = {
            row.payload["locator"]["path"]
            for row in self.session.query(HarvestInput).all()
        }
        self.assertEqual(paths, {"docs/auth.md", "docs/new.md"})
        self.assertEqual(written, 2)
        self.assertEqual(summary.files_seen, 2)
        checkpoint = self.store.load(self.config.id)
        assert checkpoint is not None
        self.assertEqual(checkpoint.last_processed_commit, head)

    def test_bootstrap_checkpoint_is_reused_on_subsequent_runs(self) -> None:
        self.write_file("docs/auth.md")
        self.commit()
        written, _ = self.harvest("bootstrap")
        self.assertEqual(written, 1)

        written, summary = self.harvest("unchanged-run")
        self.assertEqual(written, 0)
        self.assertEqual(summary.files_seen, 0)
        self.assertEqual(self.session.query(HarvestInput).count(), 1)

        self.write_file("docs/new.md")
        head = self.commit()
        written, summary = self.harvest("changed-run")
        self.assertEqual(written, 1)
        self.assertEqual(summary.files_seen, 1)
        rows = (
            self.session.query(HarvestInput)
            .filter_by(pipeline_run_id="changed-run")
            .all()
        )
        self.assertEqual(
            [row.payload["locator"]["path"] for row in rows], ["docs/new.md"]
        )
        checkpoint = self.store.load(self.config.id)
        assert checkpoint is not None
        self.assertEqual(checkpoint.last_processed_commit, head)

    def test_rejects_invalid_or_non_commit_revisions(self) -> None:
        self.write_file("docs/auth.md")
        self.commit()
        for revision in (
            "missing-revision",
            "--help",
            "HEAD^{tree}",
            "HEAD:docs/auth.md",
        ):
            with self.subTest(revision=revision):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.detector.get_tracked_files(revision)

    def test_lists_files_in_sha256_repository(self) -> None:
        self.root = self.root / "sha256"
        self.root.mkdir()
        self.git("init", "--initial-branch=main", "--object-format=sha256")
        self.write_file("docs/auth.md")
        head = self.commit()
        client = GitRepositoryClient("OWASP", "fixture", local_path=self.root)

        self.assertEqual(len(head), 64)
        self.assertEqual(
            ChangeDetector(client).get_tracked_files(head), ["docs/auth.md"]
        )


if __name__ == "__main__":
    unittest.main()
