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

    def test_path_exclusion(self):
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
                ".github/workflows/README.md",
                "node_modules/react/README.md",
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

    def test_nested_directory_globs(self):
        file_filter = FileFilter()

        result = file_filter.filter_files(
            [
                ".github/README.md",
                "packages/site/node_modules/README.md",
                "docs/archive/old.md",
                ".cursor/rules/project.md",
                "docs/setup.md",
            ]
        )

        self.assertEqual(result, ["docs/setup.md"])

    def test_explicit_empty_exclusions(self):
        file_filter = FileFilter(exclude_patterns=[])

        result = file_filter.filter_files(
            [
                ".github/README.md",
            ]
        )

        self.assertEqual(
            result,
            [".github/README.md"],
        )

    def test_default_instance_isolation(self):
        first = FileFilter()
        second = FileFilter()

        first.exclude_patterns.append("**/foo/**")

        self.assertNotIn(
            "**/foo/**",
            second.exclude_patterns,
        )


if __name__ == "__main__":
    unittest.main()
