import unittest

from application.utils.harvester.filtering_metrics import (
    FilteringMetricsCollector,
)


class FilteringMetricsCollectorTests(unittest.TestCase):
    def test_filtering_metrics_collection(self):
        collector = FilteringMetricsCollector()

        collector.record_retained()
        collector.record_retained()
        collector.record_filtered()

        metrics = collector.build()

        self.assertEqual(
            metrics.total_files,
            3,
        )

        self.assertEqual(
            metrics.retained_files,
            2,
        )

        self.assertEqual(
            metrics.filtered_files,
            1,
        )


if __name__ == "__main__":
    unittest.main()
