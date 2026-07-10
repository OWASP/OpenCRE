from datetime import UTC, datetime
import unittest

from application.utils.harvester.diff_parser import (
    DiffParser,
)

TEST_REPOSITORY = "OWASP/ASVS"
TEST_COMMIT_SHA = "abc123"
TEST_COMMITTED_AT = datetime.now(UTC)


class DiffParserTests(unittest.TestCase):
    def test_single_file_diff(self):
        parser = DiffParser()

        diff = """diff --git a/test.md b/test.md
--- a/test.md
+++ b/test.md
@@
-old
+new
+another
"""

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 1)

        self.assertEqual(
            blocks[0].file_path,
            "test.md",
        )

        self.assertEqual(
            blocks[0].added_lines,
            [
                "new",
                "another",
            ],
        )

        self.assertEqual(blocks[0].repository, TEST_REPOSITORY)
        self.assertEqual(blocks[0].commit_sha, TEST_COMMIT_SHA)
        self.assertEqual(blocks[0].committed_at, TEST_COMMITTED_AT)

    def test_multiple_files(self):
        parser = DiffParser()

        diff = """diff --git a/a.md b/a.md
@@
+one
diff --git a/b.md b/b.md
@@
+two
"""

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].file_path, "a.md")
        self.assertEqual(blocks[1].file_path, "b.md")

        self.assertEqual(blocks[0].repository, TEST_REPOSITORY)
        self.assertEqual(blocks[1].repository, TEST_REPOSITORY)

    def test_deleted_lines_are_ignored(self):
        parser = DiffParser()

        diff = """diff --git a/test.md b/test.md
@@
-old
+new
"""

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(
            blocks[0].added_lines,
            [
                "new",
            ],
        )


if __name__ == "__main__":
    unittest.main()
