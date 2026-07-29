import unittest

from application.utils.harvester.file_filter import (
    FileFilter,
)


class FileFilterTests(unittest.TestCase):
    def test_extension_filtering(self):
        file_filter = FileFilter()

        result = file_filter.filter_files(
            [
                "README.md",
                "image.png",
                "script.js",
            ]
        )

        self.assertEqual(
            result,
            ["README.md"],
        )

    def test_regex_filtering(self):
        file_filter = FileFilter()

        result = file_filter.filter_files(
            [
                ".github/workflows/test.yml",
                "docs/setup.md",
            ]
        )

        self.assertEqual(
            result,
            ["docs/setup.md"],
        )

    def test_combined_filtering(self):
        file_filter = FileFilter()

        result = file_filter.filter_files(
            [
                "README.md",
                ".github/workflows/test.yml",
                "node_modules/react/index.js",
                "docs/setup.md",
            ]
        )

        self.assertEqual(
            result,
            [
                "README.md",
                "docs/setup.md",
            ],
        )

    def test_empty_overrides_are_respected(self):
        file_filter = FileFilter(
            exclude_patterns=[],
            allowed_extensions=set(),
        )

        result = file_filter.filter_files(
            [
                "README.md",
                "image.png",
            ]
        )

        self.assertEqual(result, [])

    def test_default_instances_are_isolated(self):
        first = FileFilter()
        second = FileFilter()

        first.exclude_patterns.append("custom")
        first.allowed_extensions.add(".pdf")

        self.assertNotIn("custom", second.exclude_patterns)
        self.assertNotIn(".pdf", second.allowed_extensions)


if __name__ == "__main__":
    unittest.main()
