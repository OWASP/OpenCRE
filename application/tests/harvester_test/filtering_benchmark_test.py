import unittest

from application.utils.harvester.file_filter import FileFilter
from application.utils.harvester.filtering_benchmark import FilteringBenchmark


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

        benchmark = FilteringBenchmark(file_filter=FileFilter())

        result = benchmark.run(files)

        self.assertEqual(result.total_files, 6)
        self.assertEqual(result.retained_files, 3)
        self.assertEqual(result.filtered_files, 3)
        self.assertEqual(result.retention_rate, 0.5)
        self.assertEqual(result.filtering_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
