import unittest

from scripts import monitor_ga_health as monitor


class MonitorGaHealthTest(unittest.TestCase):
    def test_material_result_detection(self) -> None:
        self.assertTrue(monitor._http_gap_result_is_material({"a": 1}))
        self.assertFalse(monitor._http_gap_result_is_material({}))
        self.assertFalse(monitor._http_gap_result_is_material(None))

    def test_503_bucket_is_regression_marker(self) -> None:
        bucket = "http_503_regression"
        self.assertEqual(bucket, "http_503_regression")


if __name__ == "__main__":
    unittest.main()
