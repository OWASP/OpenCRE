import unittest

from application.utils.harvester.deduplication_metrics import DeduplicationMetrics
from application.utils.harvester.models import DeduplicationStatus


class DeduplicationMetricsTests(unittest.TestCase):
    def test_records_new_document(self):
        metrics = DeduplicationMetrics()

        metrics.record(DeduplicationStatus.NEW)

        self.assertEqual(metrics.total_artifacts_scanned, 1)
        self.assertEqual(metrics.artifacts_new, 1)
        self.assertEqual(metrics.artifacts_emitted, 1)

    def test_records_updated_document(self):
        metrics = DeduplicationMetrics()

        metrics.record(DeduplicationStatus.UPDATED)

        self.assertEqual(metrics.artifacts_updated, 1)
        self.assertEqual(metrics.artifacts_emitted, 1)

    def test_records_unchanged_document(self):
        metrics = DeduplicationMetrics()

        metrics.record(DeduplicationStatus.UNCHANGED)

        self.assertEqual(metrics.artifacts_unchanged, 1)
        self.assertEqual(metrics.artifacts_skipped, 1)


if __name__ == "__main__":
    unittest.main()
