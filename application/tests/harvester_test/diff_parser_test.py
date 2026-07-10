import unittest

from application.utils.harvester.diff_parser import (
    DiffParser,
)


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

        blocks = parser.parse(diff)

        self.assertEqual(
            len(blocks),
            1,
        )

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

    def test_multiple_files(self):
        parser = DiffParser()

        diff = """diff --git a/a.md b/a.md
@@
+one
diff --git a/b.md b/b.md
@@
+two
"""

        blocks = parser.parse(diff)

        self.assertEqual(
            len(blocks),
            2,
        )

        self.assertEqual(
            blocks[0].file_path,
            "a.md",
        )

        self.assertEqual(
            blocks[1].file_path,
            "b.md",
        )

    def test_deleted_lines_are_ignored(self):
        parser = DiffParser()

        diff = """diff --git a/test.md b/test.md
@@
-old
+new
"""

        blocks = parser.parse(diff)

        self.assertEqual(
            blocks[0].added_lines,
            [
                "new",
            ],
        )


if __name__ == "__main__":
    unittest.main()
