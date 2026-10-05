from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

from application.utils.harvester.change_detector import (
    ChangeDetector,
)


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
