"""Unit tests for point-and-shoot GitHub URL ingest helpers."""

from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import create_app, sqla
from application.database.db import KnowledgeQueueItem
from application.utils.harvester import github_url_ingest as ingest
from application.utils.harvester.github_url_ingest import (
    format_knowledge_item,
    parse_github_url,
)
from application.utils.noise_filter.queue_writer import write_verdicts
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult


class ParseGitHubUrlTests(unittest.TestCase):
    def test_owner_repo(self) -> None:
        p = parse_github_url("https://github.com/OWASP/ASVS")
        self.assertEqual(p.owner, "OWASP")
        self.assertEqual(p.repo, "ASVS")
        self.assertIsNone(p.branch)
        self.assertIsNone(p.path_prefix)

    def test_git_suffix_and_www(self) -> None:
        p = parse_github_url("https://www.github.com/OWASP/ASVS.git")
        self.assertEqual(p.owner, "OWASP")
        self.assertEqual(p.repo, "ASVS")

    def test_tree_branch_and_path(self) -> None:
        p = parse_github_url("https://github.com/OWASP/ASVS/tree/master/5.0/en")
        self.assertEqual(p.branch, "master")
        self.assertEqual(p.path_prefix, "5.0/en")

    def test_rejects_non_github(self) -> None:
        with self.assertRaises(ValueError):
            parse_github_url("https://gitlab.com/OWASP/ASVS")

    def test_rejects_unsafe_owner_repo_and_branch(self) -> None:
        for bad in (
            "https://github.com/OWASP/..",
            "https://github.com/-bad/ASVS",
            "https://github.com/OWASP/AS%56S",
            "https://github.com/OWASP/ASVS/tree/a..b/x",
        ):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                parse_github_url(bad)


class FormatKnowledgeItemTests(unittest.TestCase):
    def test_includes_path_and_label(self) -> None:
        out = format_knowledge_item(
            path="5.0/en/V1.md",
            label="KNOWLEDGE",
            confidence=0.91,
            text="Verify that input is sanitized.",
            reasoning="looks like a control",
        )
        self.assertIn("path: 5.0/en/V1.md", out)
        self.assertIn("label: KNOWLEDGE", out)
        self.assertIn("Verify that input is sanitized.", out)


if __name__ == "__main__":
    unittest.main()


def _tarball(path: Path, members: dict) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


class DownloadTarballTests(unittest.TestCase):
    def test_explicit_branch_does_not_fall_back(self) -> None:
        requested = []

        def fake_download(url: str, dest: Path) -> None:
            requested.append(url)
            raise OSError("404")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ingest, "_download_to_file", side_effect=fake_download
        ):
            with self.assertRaises(RuntimeError):
                ingest._download_tarball(
                    "OWASP",
                    "ASVS",
                    "release",
                    Path(tmp) / "x.tgz",
                    allow_fallback=False,
                )
        self.assertEqual(len(requested), 1)
        self.assertTrue(requested[0].endswith("/tar.gz/refs/heads/release"))

    def test_default_branch_falls_back_to_main_and_master(self) -> None:
        requested = []

        def fake_download(url: str, dest: Path) -> None:
            requested.append(url.rsplit("/", 1)[-1])
            raise OSError("404")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ingest, "_download_to_file", side_effect=fake_download
        ):
            with self.assertRaises(RuntimeError):
                ingest._download_tarball("OWASP", "ASVS", "dev", Path(tmp) / "x.tgz")
        self.assertEqual(requested, ["dev", "main", "master"])


class IterMdLimitsTests(unittest.TestCase):
    def test_oversized_member_is_skipped(self) -> None:
        small = b"# Title\n" + b"security requirement text " * 5
        big = b"x" * (ingest.MAX_MD_MEMBER_BYTES + 1)
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / "a.tgz"
            _tarball(tgz, {"repo-main/ok.md": small, "repo-main/big.md": big})
            found = ingest._iter_md(tgz, path_prefix=None)
        self.assertEqual([rel for rel, _ in found], ["ok.md"])

    def test_total_bytes_cap_stops_reading(self) -> None:
        body = b"# T\n" + b"security requirement text " * 8
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ingest, "MAX_MD_TOTAL_BYTES", len(body) + 1
        ):
            tgz = Path(tmp) / "a.tgz"
            _tarball(tgz, {f"repo-main/{i}.md": body for i in range(3)})
            found = ingest._iter_md(tgz, path_prefix=None)
        self.assertEqual(len(found), 1)


def _queue_record(run_id: str, text: str) -> ChangeRecord:
    return ChangeRecord.model_validate(
        {
            "schema_version": "0.2.0",
            "chunk_id": f"chk-{run_id}",
            "artifact_id": f"art:{run_id}",
            "pipeline_run_id": run_id,
            "text": text,
            "span": {"index": 0, "total": 1, "heading_path": []},
            "source": {
                "type": "github",
                "repo": "OWASP/Test",
                "commit_sha": "abc123",
                "committed_at": "2026-07-17T00:00:00Z",
            },
            "locator": {"kind": "repo_path", "id": "p.md", "path": "p.md"},
        }
    )


class IngestQueueScopingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        verdict = ClassifyResult(label="KNOWLEDGE", confidence=0.9, reasoning="r")
        write_verdicts(
            sqla.session,
            [
                (_queue_record("harvest-1", "harvested requirement"), verdict, "h-a"),
                (
                    _queue_record("ingest-old", "older ingest requirement"),
                    verdict,
                    "h-b",
                ),
            ],
        )
        sqla.session.commit()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _run_ids(self) -> set:
        return {r.pipeline_run_id for r in KnowledgeQueueItem.query.all()}

    def test_failed_download_keeps_all_rows(self) -> None:
        with patch.object(ingest, "TARBALL_DIR", Path(self.tmp.name)), patch.object(
            ingest, "_download_to_file", side_effect=OSError("down")
        ):
            counts = ingest.ingest_github_url(
                "https://github.com/OWASP/Test",
                session=sqla.session,
                cache_file="",
                keep_all=True,
            )
        self.assertEqual(counts.errors, 1)
        self.assertEqual(self._run_ids(), {"harvest-1", "ingest-old"})

    def test_successful_ingest_replaces_only_prior_ingest_rows(self) -> None:
        body = (
            b"# Authentication\n\n"
            b"Verify that all authentication controls fail securely and log failures.\n"
        )

        def fake_download(url: str, dest: Path) -> None:
            _tarball(dest, {"Test-main/V1.md": body})

        with patch.object(ingest, "TARBALL_DIR", Path(self.tmp.name)), patch.object(
            ingest, "_download_to_file", side_effect=fake_download
        ):
            counts = ingest.ingest_github_url(
                "https://github.com/OWASP/Test",
                session=sqla.session,
                cache_file="",
                keep_all=True,
                run_id="ingest-new",
            )
        self.assertEqual(counts.errors, 0)
        self.assertEqual(self._run_ids(), {"harvest-1", "ingest-new"})
