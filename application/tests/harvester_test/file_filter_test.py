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


if __name__ == "__main__":
    unittest.main()
