import unittest

from application.utils import wayfinder_metadata


class TestWayfinderMetadata(unittest.TestCase):
    def test_noise_resource_detection(self):
        self.assertTrue(wayfinder_metadata.is_noise_resource("standard", "Standard"))
        self.assertTrue(wayfinder_metadata.is_noise_resource("Tool", "Tool"))
        self.assertTrue(wayfinder_metadata.is_noise_resource("", "Standard"))
        self.assertFalse(wayfinder_metadata.is_noise_resource("ASVS", "Standard"))

    def test_canonical_resource_name(self):
        self.assertEqual(
            wayfinder_metadata.canonical_resource_name("cwe-22", "Standard"), "CWE"
        )
        self.assertEqual(
            wayfinder_metadata.canonical_resource_name("capec-111", "Standard"),
            "CAPEC",
        )
        self.assertEqual(
            wayfinder_metadata.canonical_resource_name("owasp top 10", "Standard"),
            "OWASP Top 10 2021",
        )
        self.assertEqual(
            wayfinder_metadata.canonical_resource_name("standard", "Standard"), ""
        )

    def test_get_wayfinder_metadata_fallback(self):
        metadata = wayfinder_metadata.get_wayfinder_metadata(
            "Unknown Framework", "Tool"
        )
        self.assertEqual(metadata["source"], "fallback")
        self.assertIn("Implementation", metadata["sdlc"])
        self.assertIn("Unknown", metadata["supporting_orgs"])
        self.assertIn("Unknown", metadata["licenses"])


if __name__ == "__main__":
    unittest.main()
