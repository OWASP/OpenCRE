from datetime import UTC, datetime
import unittest

from application.utils.harvester.diff_parser import (
    DiffParser,
)

TEST_REPOSITORY = "OWASP/ASVS"
TEST_COMMIT_SHA = "abc123"
TEST_COMMITTED_AT = datetime.now(UTC)


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

    def test_non_ascii_path_is_decoded(self):
        """Git C-quotes non-ASCII paths; the diff must not be dropped."""
        parser = DiffParser()

        diff = (
            'diff --git "a/caf\\303\\251.md" "b/caf\\303\\251.md"\n'
            "index a29bdeb..5bafbad 100644\n"
            '--- "a/caf\\303\\251.md"\n'
            '+++ "b/caf\\303\\251.md"\n'
            "@@ -1 +1,2 @@\n"
            " line1\n"
            "+added line\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].file_path, "café.md")
        self.assertEqual(blocks[0].added_lines, ["added line"])

    def test_unescaped_non_ascii_in_quoted_path_is_preserved(self):
        """With core.quotePath=false git quotes but leaves UTF-8 bytes raw."""
        parser = DiffParser()

        # File literally named: café".md — the quote forces quoting, the
        # accented character stays unescaped.
        diff = (
            'diff --git "a/café\\".md" "b/café\\".md"\n'
            '--- "a/café\\".md"\n'
            '+++ "b/café\\".md"\n'
            "@@ -1 +1,2 @@\n"
            " line1\n"
            "+added line\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].file_path, 'café".md')
        self.assertEqual(blocks[0].added_lines, ["added line"])

    def test_path_containing_separator_sequence_is_not_truncated(self):
        """A path may itself contain " b/", which must not split the header."""
        parser = DiffParser()

        diff = (
            "diff --git a/foo b/bar.md b/foo b/bar.md\n"
            "index 587be6b..aee5fdc 100644\n"
            "--- a/foo b/bar.md\t\n"
            "+++ b/foo b/bar.md\t\n"
            "@@ -1 +1,2 @@\n"
            " x\n"
            "+more\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].file_path, "foo b/bar.md")
        self.assertEqual(blocks[0].added_lines, ["more"])

    def test_quoted_file_header_is_not_treated_as_added_content(self):
        """A quoted ``+++ "b/..."`` header starts with '+' but is metadata."""
        parser = DiffParser()

        diff = (
            'diff --git "a/caf\\303\\251.md" "b/caf\\303\\251.md"\n'
            '--- "a/caf\\303\\251.md"\n'
            '+++ "b/caf\\303\\251.md"\n'
            "@@ -1 +1,2 @@\n"
            "+only real content\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(blocks[0].added_lines, ["only real content"])

    def test_added_line_starting_with_plus_is_kept(self):
        """``+++ x`` inside a hunk is an added line reading ``++ x``."""
        parser = DiffParser()

        diff = (
            "diff --git a/test.md b/test.md\n"
            "--- a/test.md\n"
            "+++ b/test.md\n"
            "@@ -1 +1,2 @@\n"
            "+++ still content\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(blocks[0].added_lines, ["++ still content"])

    def test_renamed_file_uses_new_path(self):
        """Added lines belong to the rename target, not the source."""
        parser = DiffParser()

        diff = (
            "diff --git a/old.md b/new.md\n"
            "similarity index 87%\n"
            "rename from old.md\n"
            "rename to new.md\n"
            "--- a/old.md\n"
            "+++ b/new.md\n"
            "@@ -1 +1,2 @@\n"
            " keep\n"
            "+added\n"
        )

        blocks = parser.parse(
            diff,
            repository=TEST_REPOSITORY,
            commit_sha=TEST_COMMIT_SHA,
            committed_at=TEST_COMMITTED_AT,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].file_path, "new.md")
        self.assertEqual(blocks[0].added_lines, ["added"])


if __name__ == "__main__":
    unittest.main()
