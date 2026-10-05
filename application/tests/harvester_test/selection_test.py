"""Repo kinds, per-kind defaults, and due/capped selection for scheduled harvests."""

from cre_logging import get_logger

logger = get_logger(__name__)

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from application import create_app, sqla
from application.utils.harvester import pipeline as harvest_pipeline
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.config_loader import load_repo_config
from application.utils.harvester.models import RepositoryCheckpoint
from application.utils.harvester.schemas import HARVESTABLE_KINDS, ReposFile
from application.utils.harvester.selection import select_repositories

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _entry(repo: str, kind: str = "project", interval: int = 60, enabled: bool = True):
    return {
        "id": f"owasp-{repo.lower()}",
        "kind": kind,
        "enabled": enabled,
        "type": "github",
        "owner": "OWASP",
        "repo": repo,
        "branch": "main",
        "paths": {"include": ["**/*.md"]},
        "chunking": {"strategy": "docling", "max_tokens": 1000},
        "polling": {"mode": "incremental", "interval_minutes": interval},
    }


def _repos(*entries) -> ReposFile:
    return ReposFile.model_validate({"repositories": list(entries)})


class KindDefaultsTests(unittest.TestCase):
    def test_kind_defaults_to_standard(self) -> None:
        cfg = _repos(
            {k: v for k, v in _entry("ASVS").items() if k != "kind"},
        )
        self.assertEqual(cfg.repositories[0].kind, "standard")

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(Exception):
            _repos(_entry("Foo", kind="blog"))

    def test_defaults_fill_missing_fields_and_entry_wins(self) -> None:
        cfg = ReposFile.model_validate(
            {
                "defaults": {
                    "project": {
                        "type": "github",
                        "owner": "OWASP",
                        "branch": "master",
                        "paths": {"include": ["**/*.md"]},
                        "chunking": {"strategy": "docling", "max_tokens": 1000},
                        "polling": {"mode": "incremental", "interval_minutes": 1440},
                    }
                },
                "repositories": [
                    {"id": "owasp-a", "kind": "project", "repo": "a"},
                    {
                        "id": "owasp-b",
                        "kind": "project",
                        "repo": "b",
                        "branch": "main",
                    },
                ],
            }
        )
        a, b = cfg.repositories
        self.assertEqual((a.owner, a.branch), ("OWASP", "master"))
        self.assertEqual(a.polling.interval_minutes, 1440)
        self.assertEqual(b.branch, "main")

    def test_shipped_repos_yaml_loads_and_routes_every_kind(self) -> None:
        cfg = load_repo_config(harvest_pipeline.DEFAULT_REPOS_YAML)
        kinds = {r.kind for r in cfg.repositories}
        self.assertIn("standard", kinds)
        self.assertTrue(kinds <= {"standard", "project", "chapter", "event", "other"})
        ids = [r.id.casefold() for r in cfg.repositories]
        self.assertEqual(len(ids), len(set(ids)))


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.store = CheckpointStore(session=sqla.session)

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _checkpoint(self, repo: str, age_minutes: int) -> None:
        self.store.save(
            RepositoryCheckpoint(
                repository_id=f"owasp-{repo.lower()}",
                last_processed_commit="abc1234",
                updated_at=NOW - timedelta(minutes=age_minutes),
                provider="github",
                owner="OWASP",
                repository=repo,
                branch="main",
            )
        )

    def test_default_kinds_are_the_curated_standards_only(self) -> None:
        cfg = _repos(
            _entry("std", kind="standard"),
            _entry("proj", kind="project"),
            _entry("other", kind="other"),
            _entry("chap", kind="chapter"),
            _entry("evt", kind="event"),
            _entry("off", kind="project", enabled=False),
        )
        sel = select_repositories(cfg.repositories, self.store, now=NOW)
        self.assertEqual([r.repo for r in sel.selected], ["std"])

    def test_harvestable_kinds_exclude_chapter_and_event(self) -> None:
        cfg = _repos(
            _entry("std", kind="standard"),
            _entry("proj", kind="project"),
            _entry("other", kind="other"),
            _entry("chap", kind="chapter"),
            _entry("evt", kind="event"),
        )
        sel = select_repositories(
            cfg.repositories, self.store, kinds=HARVESTABLE_KINDS, now=NOW
        )
        self.assertEqual([r.repo for r in sel.selected], ["std", "proj", "other"])

    def test_explicit_kinds_filter(self) -> None:
        cfg = _repos(_entry("std", kind="standard"), _entry("proj", kind="project"))
        sel = select_repositories(
            cfg.repositories, self.store, kinds={"project"}, now=NOW
        )
        self.assertEqual([r.repo for r in sel.selected], ["proj"])

    def test_only_due_skips_fresh_checkpoints(self) -> None:
        cfg = _repos(
            _entry("fresh", interval=60),
            _entry("stale", interval=60),
            _entry("never", interval=60),
        )
        self._checkpoint("fresh", age_minutes=10)
        self._checkpoint("stale", age_minutes=61)
        sel = select_repositories(
            cfg.repositories,
            self.store,
            kinds=HARVESTABLE_KINDS,
            only_due=True,
            now=NOW,
        )
        self.assertEqual([r.repo for r in sel.selected], ["never", "stale"])
        self.assertEqual(sel.skipped_not_due, 1)

    def test_not_only_due_includes_fresh(self) -> None:
        cfg = _repos(_entry("fresh", interval=60))
        self._checkpoint("fresh", age_minutes=1)
        sel = select_repositories(
            cfg.repositories, self.store, kinds=HARVESTABLE_KINDS, now=NOW
        )
        self.assertEqual([r.repo for r in sel.selected], ["fresh"])

    def test_max_repos_keeps_never_harvested_then_stalest_and_counts_deferred(
        self,
    ) -> None:
        cfg = _repos(
            _entry("old", interval=10),
            _entry("older", interval=10),
            _entry("never", interval=10),
        )
        self._checkpoint("old", age_minutes=100)
        self._checkpoint("older", age_minutes=500)
        sel = select_repositories(
            cfg.repositories,
            self.store,
            kinds=HARVESTABLE_KINDS,
            only_due=True,
            max_repos=2,
            now=NOW,
        )
        self.assertEqual([r.repo for r in sel.selected], ["never", "older"])
        self.assertEqual(sel.deferred, 1)


class RunHarvesterSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.tmp = tempfile.TemporaryDirectory()
        self.yaml = Path(self.tmp.name) / "repos.yaml"
        self.yaml.write_text(
            """
defaults:
  project:
    type: github
    owner: OWASP
    branch: main
    paths: {include: ["**/*.md"]}
    chunking: {strategy: docling, max_tokens: 1000}
    polling: {mode: incremental, interval_minutes: 60}
  chapter:
    type: github
    owner: OWASP
    branch: main
    paths: {include: ["index.md"]}
    chunking: {strategy: docling, max_tokens: 1000}
    polling: {mode: incremental, interval_minutes: 1440}
repositories:
  - {id: owasp-p1, kind: project, repo: p1}
  - {id: owasp-p2, kind: project, repo: p2}
  - {id: owasp-c1, kind: chapter, repo: www-chapter-x}
"""
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_default_run_visits_no_project_repos(self) -> None:
        visited = []
        with patch.object(
            harvest_pipeline,
            "_harvest_repository",
            lambda **kw: visited.append(kw["repo_cfg"].id) or 0,
        ):
            summary = harvest_pipeline.run_harvester(
                sqla.session, "run-0", repos_yaml=self.yaml
            )
        self.assertEqual(visited, [])
        self.assertEqual(summary.repositories, 0)

    def test_only_selected_repositories_are_harvested_and_reported(self) -> None:
        visited = []

        def fake_harvest(*, repo_cfg, **_kwargs):
            visited.append(repo_cfg.id)
            return 3

        with patch.object(harvest_pipeline, "_harvest_repository", fake_harvest):
            summary = harvest_pipeline.run_harvester(
                sqla.session,
                "run-1",
                repos_yaml=self.yaml,
                kinds=HARVESTABLE_KINDS,
                only_due=True,
                max_repos=1,
                now=NOW,
            )
        self.assertEqual(visited, ["owasp-p1"])
        self.assertEqual(summary.repository_ids, ["owasp-p1"])
        self.assertEqual(summary.repositories, 1)
        self.assertEqual(summary.deferred, 1)
        self.assertEqual(summary.chunks_written, 3)
        self.assertEqual(summary.status, "ok")


if __name__ == "__main__":
    unittest.main()
