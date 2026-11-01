from cre_logging import get_logger

logger = get_logger(__name__)

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

from application.utils.harvester.change_detector import (
    ChangeDetector,
)
from application.utils.harvester.pipeline import resolve_base_commit


class ChangeDetectorTests(unittest.TestCase):
    @patch("application.utils.harvester.change_detector.subprocess.run")
    def test_get_modified_files_since(self, mock_run):
        client = MagicMock()
        client.get_local_path.return_value = "repo-under-test"

        mock_run.side_effect = [
            MagicMock(stdout="resolved_base\n"),
            MagicMock(stdout="resolved_target\n"),
            MagicMock(stdout="a.md\nb.md\na.md\n"),
        ]

        detector = ChangeDetector(client)

        files = detector.get_modified_files_since(
            "base",
            "target",
        )

        self.assertEqual(
            files,
            [
                "a.md",
                "b.md",
            ],
        )

        mock_run.assert_has_calls(
            [
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "base^{commit}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "target^{commit}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "diff",
                        "--name-only",
                        "resolved_base",
                        "resolved_target",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
            ]
        )

    @patch("application.utils.harvester.change_detector.subprocess.run")
    def test_get_commits_since(self, mock_run):
        client = MagicMock()
        client.get_local_path.return_value = "repo-under-test"

        mock_run.side_effect = [
            MagicMock(stdout="resolved_base\n"),
            MagicMock(stdout="resolved_target\n"),
            MagicMock(stdout="111\n222\n333\n"),
        ]

        detector = ChangeDetector(client)

        commits = detector.get_commits_since(
            "base",
            "target",
        )

        self.assertEqual(
            commits,
            [
                "111",
                "222",
                "333",
            ],
        )

        self.assertEqual(
            mock_run.call_args_list,
            [
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "base^{commit}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "target^{commit}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "repo-under-test",
                        "log",
                        "--reverse",
                        "--format=%H",
                        "resolved_base..resolved_target",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                ),
            ],
        )


def _git(*args: str, cwd: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class ShallowCloneCheckpointTests(unittest.TestCase):
    """The harvester clones with --depth 1, so a persisted checkpoint commit may
    be absent from a freshly (re)created clone."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.source = str(root / "source")
        Path(self.source).mkdir()
        _git("init", "-q", "-b", "main", cwd=self.source)
        (Path(self.source) / "a.md").write_text("one\n")
        _git("add", ".", cwd=self.source)
        _git("commit", "-q", "-m", "first", cwd=self.source)
        self.first = _git("rev-parse", "HEAD", cwd=self.source)
        (Path(self.source) / "a.md").write_text("two\n")
        _git("commit", "-q", "-am", "second", cwd=self.source)
        self.second = _git("rev-parse", "HEAD", cwd=self.source)

        self.clone = str(root / "clone")
        _git(
            "clone",
            "-q",
            "--depth",
            "1",
            f"file://{self.source}",
            self.clone,
            cwd=self._tmp.name,
        )
        client = MagicMock()
        client.get_local_path.return_value = self.clone
        self.detector = ChangeDetector(client)

    def test_commit_exists_true_for_commit_in_shallow_clone(self) -> None:
        self.assertTrue(self.detector.commit_exists(self.second))

    def test_commit_exists_false_for_commit_outside_shallow_history(self) -> None:
        self.assertFalse(self.detector.commit_exists(self.first))

    def test_commit_exists_false_for_unknown_or_option_like_value(self) -> None:
        self.assertFalse(self.detector.commit_exists("0" * 40))
        self.assertFalse(self.detector.commit_exists("--all"))
        self.assertFalse(self.detector.commit_exists(""))

    def test_resolve_base_commit_falls_back_to_full_harvest(self) -> None:
        self.assertIsNone(resolve_base_commit(self.detector, self.first, "repo-x"))

    def test_resolve_base_commit_keeps_reachable_checkpoint(self) -> None:
        self.assertEqual(
            resolve_base_commit(self.detector, self.second, "repo-x"), self.second
        )

    def test_resolve_base_commit_keeps_missing_checkpoint_as_none(self) -> None:
        self.assertIsNone(resolve_base_commit(self.detector, None, "repo-x"))


if __name__ == "__main__":
    unittest.main()


class ListFilesAtCommitTests(unittest.TestCase):
    """First-run harvests list the whole tree; the empty tree is not a commit."""

    def test_lists_every_tracked_file_in_a_real_repository(self):
        import subprocess
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "-q")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            git("config", "commit.gpgsign", "false")
            (repo / "docs").mkdir()
            (repo / "docs" / "a.md").write_text("a")
            (repo / "b.md").write_text("b")
            git("add", ".")
            git("commit", "-q", "-m", "init")
            head = git("rev-parse", "HEAD")

            client = MagicMock()
            client.get_local_path.return_value = repo
            files = ChangeDetector(client).get_files_at_commit(head)

        self.assertEqual(files, ["b.md", "docs/a.md"])
