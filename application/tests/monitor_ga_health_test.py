import io
import unittest
import urllib.error
from unittest import mock

from scripts import monitor_ga_health as monitor


class MonitorGaHealthTest(unittest.TestCase):
    def test_material_result_detection(self) -> None:
        self.assertTrue(monitor._http_gap_result_is_material({"a": 1}))
        self.assertFalse(monitor._http_gap_result_is_material({}))
        self.assertFalse(monitor._http_gap_result_is_material(None))

    def test_check_pair_503_uses_regression_bucket(self) -> None:
        body = b"Service Unavailable"

        def _raise_503(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "http://example", 503, "Service Unavailable", {}, io.BytesIO(body)
            )

        with mock.patch("urllib.request.urlopen", side_effect=_raise_503):
            result = monitor._check_pair("https://opencre.org/rest/v1", "A", "B", 10)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["bucket"], "http_503_regression")
        self.assertEqual(result["status_code"], 503)


if __name__ == "__main__":
    unittest.main()
