import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from application.utils.harvester.change_detector import (
    ChangeDetector,
)


class ChangeDetectorTests(unittest.TestCase):
    @patch("application.utils.harvester.change_detector.subprocess.run")
    def test_get_modified_files_since(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="a.md\nb.md\na.md\n",
        )

        client = MagicMock()
        detector = ChangeDetector(client)

        files = detector.get_modified_files_since("abc123")

        self.assertEqual(
            files,
            [
                "a.md",
                "b.md",
            ],
        )

    @patch("application.utils.harvester.change_detector.subprocess.run")
    def test_get_commits_since(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="111\n222\n333\n",
        )

        client = MagicMock()
        detector = ChangeDetector(client)

        commits = detector.get_commits_since("abc123")

        self.assertEqual(
            commits,
            [
                "111",
                "222",
                "333",
            ],
        )


if __name__ == "__main__":
    unittest.main()
