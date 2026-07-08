import unittest

from application.utils.harvester.file_filter import (
    FileFilter,
)
from application.utils.harvester.models import (
    FilteringMetrics,
)


class FilteringBenchmarkTests(unittest.TestCase):
    def test_filtering_benchmark(self):
        files = [
            "README.md",
            ".github/workflows/ci.yml",
            "docs/guide.md",
            "image.png",
            "notes.txt",
            "package-lock.json",
        ]

        file_filter = FileFilter()

        retained_files = file_filter.filter_files(files)

        metrics = FilteringMetrics(
            total_files=len(files),
            retained_files=len(retained_files),
            filtered_files=len(files) - len(retained_files),
        )

        self.assertEqual(
            metrics.total_files,
            6,
        )

        self.assertEqual(
            metrics.retained_files,
            3,
        )

        self.assertEqual(
            metrics.filtered_files,
            3,
        )


if __name__ == "__main__":
    unittest.main()
