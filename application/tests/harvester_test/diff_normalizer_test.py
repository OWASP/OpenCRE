import unittest

from application.utils.harvester.diff_normalizer import (
    DiffNormalizer,
)

from application.utils.harvester.models import (
    DiffBlock,
)


class DiffNormalizerTests(unittest.TestCase):
    def test_whitespace_normalization(self):
        normalizer = DiffNormalizer()

        blocks = [
            DiffBlock(
                file_path="README.md",
                added_lines=[
                    "     Hello      World      ",
                    "\t\tTabs\t\tEverywhere\t",
                    "",
                    "     ",
                    "Unicode\u00a0Space",
                    "Mix\t of\t tabs   and    spaces",
                    "   Multiple     words      together   ",
                    "\u00a0\u00a0Leading unicode spaces\u00a0",
                    "   ## Authentication   ",
                    "   -   Use MFA   ",
                    "   `inline code`   ",
                    "   **Important**   ",
                ],
            )
        ]

        result = normalizer.normalize(blocks)

        self.assertEqual(
            result[0].added_lines,
            [
                "Hello World",
                "Tabs Everywhere",
                "Unicode Space",
                "Mix of tabs and spaces",
                "Multiple words together",
                "Leading unicode spaces",
                "## Authentication",
                "- Use MFA",
                "`inline code`",
                "**Important**",
            ],
        )

    def test_remove_empty_lines(self):
        normalizer = DiffNormalizer()

        blocks = [
            DiffBlock(
                file_path="README.md",
                added_lines=[
                    "",
                    "   ",
                    "Hello",
                ],
            )
        ]

        result = normalizer.normalize(blocks)

        self.assertEqual(
            result[0].added_lines,
            [
                "Hello",
            ],
        )

    def test_multiple_blocks(self):
        normalizer = DiffNormalizer()

        blocks = [
            DiffBlock(
                file_path="a.md",
                added_lines=["  One  "],
            ),
            DiffBlock(
                file_path="b.md",
                added_lines=["  Two  "],
            ),
        ]

        result = normalizer.normalize(blocks)

        self.assertEqual(
            result[0].added_lines,
            ["One"],
        )

        self.assertEqual(
            result[1].added_lines,
            ["Two"],
        )


if __name__ == "__main__":
    unittest.main()
