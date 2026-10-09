"""artifact_id / repo_ids filters for OIE RQ fan-out."""

from __future__ import annotations

import unittest

from application import create_app, sqla
from application.database.db import HarvestInput, KnowledgeQueueItem
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.schemas import ReposFile
from application.utils.harvester.selection import select_repositories
from application.utils.librarian.knowledge_source import DbKnowledgeSource
from application.utils.noise_filter.schemas import ClassifyResult
from application.utils.noise_filter.pipeline import run_noise_filter


def _entry(repo: str, kind: str = "standard"):
    return {
        "id": f"owasp-{repo.lower()}",
        "kind": kind,
        "enabled": True,
        "type": "github",
        "owner": "OWASP",
        "repo": repo,
        "branch": "main",
        "paths": {"include": ["**/*.md"]},
        "chunking": {"strategy": "docling", "max_tokens": 1000},
        "polling": {"mode": "incremental", "interval_minutes": 60},
    }


def _payload(artifact: str, path: str = "document/x.md"):
    return {
        "schema_version": "0.2.0",
        "chunk_id": f"chk:{path}:{artifact}",
        "artifact_id": artifact,
        "pipeline_run_id": "run1",
        "text": "security testing content",
        "span": {"index": 0, "total": 1, "heading_path": []},
        "source": {
            "type": "github",
            "repo": "OWASP/test",
            "commit_sha": "abc123",
            "committed_at": "2026-07-17T00:00:00Z",
        },
        "locator": {"kind": "repo_path", "id": path, "path": path},
    }


class _FakeClassifier:
    def __init__(self, verdicts):
        self.verdicts = verdicts

    def classify_batch(self, records):
        assert len(records) == len(self.verdicts)
        return list(self.verdicts)


class RepoIdsSelectionTests(unittest.TestCase):
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

    def test_repo_ids_restricts_selection(self) -> None:
        cfg = ReposFile.model_validate(
            {"repositories": [_entry("ASVS"), _entry("AISVS")]}
        )
        sel = select_repositories(
            cfg.repositories,
            self.store,
            kinds={"standard"},
            repo_ids={"owasp-asvs"},
        )
        self.assertEqual([r.id for r in sel.selected], ["owasp-asvs"])


class ArtifactIdFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_noise_filter_scopes_to_artifact(self) -> None:
        for art, path in (("art:a", "a.md"), ("art:b", "b.md")):
            sqla.session.add(
                HarvestInput(
                    pipeline_run_id="run1",
                    status="pending",
                    artifact_id=art,
                    source_repo="OWASP/test",
                    payload=_payload(art, path),
                )
            )
        sqla.session.commit()
        clf = _FakeClassifier(
            [ClassifyResult(label="KNOWLEDGE", confidence=0.9, reasoning="r")]
        )
        s = run_noise_filter(sqla.session, "run1", classifier=clf, artifact_id="art:a")
        self.assertEqual(s.read, 1)
        self.assertEqual(s.kept_knowledge, 1)
        self.assertEqual(
            HarvestInput.query.filter_by(
                artifact_id="art:a", status="processed"
            ).count(),
            1,
        )
        self.assertEqual(
            HarvestInput.query.filter_by(artifact_id="art:b", status="pending").count(),
            1,
        )

    def test_knowledge_source_scopes_to_artifact(self) -> None:
        for art in ("art:a", "art:b"):
            sqla.session.add(
                KnowledgeQueueItem(
                    content_hash=f"hash-{art}",
                    chunk_id=f"chk:{art}",
                    artifact_id=art,
                    pipeline_run_id="run1",
                    schema_version="0.2.0",
                    source_type="github",
                    source_repo="OWASP/test",
                    source_commit_sha="abc1234",
                    locator_kind="repo_path",
                    locator_path="x.md",
                    span_index=0,
                    span_total=1,
                    text="security",
                    llm_label="KNOWLEDGE",
                    confidence=0.9,
                )
            )
        sqla.session.commit()
        src = DbKnowledgeSource(
            sqla.session, pipeline_run_id="run1", artifact_id="art:a"
        )
        items = list(src.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].artifact_id, "art:a")

    def test_blank_artifact_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_noise_filter(sqla.session, "run1", artifact_id="  ")


if __name__ == "__main__":
    unittest.main()
