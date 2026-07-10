import unittest
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

from application.utils.harvester.diff_retriever import (
    DiffRetriever,
)


class DiffRetrieverTests(unittest.TestCase):
    @patch("application.utils.harvester.diff_retriever.subprocess.run")
    def test_get_diff(self, mock_run):
        mock_run.side_effect = [
            MagicMock(stdout="abc123\n"),
            MagicMock(stdout="def456\n"),
            MagicMock(stdout=b"diff --git a/README.md b/README.md\n"),
        ]

        client = MagicMock()
        client.get_local_path.return_value = "/tmp/repo"

        retriever = DiffRetriever(client)
        diff = retriever.get_diff(
            "abc123",
            "def456",
        )

        self.assertEqual(
            diff,
            "diff --git a/README.md b/README.md\n",
        )

        mock_run.assert_has_calls(
            [
                call(
                    [
                        "git",
                        "-C",
                        "/tmp/repo",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "abc123^{commit}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "/tmp/repo",
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        "def456^{commit}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                ),
                call(
                    [
                        "git",
                        "-C",
                        "/tmp/repo",
                        "diff",
                        "abc123",
                        "def456",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=300,
                ),
            ]
        )

    @patch("application.utils.harvester.diff_retriever.subprocess.run")
    def test_large_diff_raises(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"A" * (51 * 1024 * 1024),
        )

        client = MagicMock()
        client.get_local_path.return_value = "/tmp/repo"

        retriever = DiffRetriever(client)

        with self.assertRaises(ValueError):
            retriever.get_diff("a", "b")


if __name__ == "__main__":
    unittest.main()
