import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from application.utils.harvester.diff_retriever import (
    DiffRetriever,
)


class DiffRetrieverTests(unittest.TestCase):
    @patch("application.utils.harvester.diff_retriever.subprocess.run")
    def test_get_diff(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="diff --git a/README.md b/README.md\n",
        )

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

        mock_run.assert_called_once_with(
            [
                "git",
                "-C",
                "/tmp/repo",
                "diff",
                "abc123",
                "def456",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )


if __name__ == "__main__":
    unittest.main()
