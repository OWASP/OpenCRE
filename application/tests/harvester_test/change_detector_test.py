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
