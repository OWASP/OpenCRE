import unittest

from application.utils import data_health


class TestDataHealth(unittest.TestCase):
    def _dataset(self, cre_id: str, child_id: str, node_id: str):
        return {
            "cre": [
                {
                    "id": cre_id,
                    "external_id": "100-100",
                    "name": "Authentication",
                    "description": "Base auth requirement",
                    "tags": "auth,session",
                },
                {
                    "id": child_id,
                    "external_id": "100-101",
                    "name": "Session timeout",
                    "description": "Timeout policy",
                    "tags": "session",
                },
            ],
            "node": [
                {
                    "id": node_id,
                    "name": "ASVS",
                    "section": "V2",
                    "subsection": "2.1.1",
                    "section_id": "ASVS-V2-2.1.1",
                    "version": "4.0",
                    "description": "ASVS mapping entry",
                    "tags": "asvs",
                    "ntype": "Standard",
                    "link": "https://example.com",
                }
            ],
            "cre_links": [
                {
                    "type": "Contains",
                    "group": cre_id,
                    "cre": child_id,
                }
            ],
            "cre_node_links": [
                {
                    "type": "Linked To",
                    "cre": child_id,
                    "node": node_id,
                }
            ],
        }

    def test_equivalent_when_only_internal_ids_differ(self):
        left_rows = self._dataset("cre-id-1", "cre-id-2", "node-id-1")
        right_rows = self._dataset("cre-id-a", "cre-id-b", "node-id-a")

        left = data_health.build_canonical_snapshot(left_rows)
        right = data_health.build_canonical_snapshot(right_rows)

        self.assertEqual(
            data_health.snapshot_digest(left), data_health.snapshot_digest(right)
        )
        self.assertEqual(data_health.snapshot_diff(left, right), {})

    def test_detects_data_change(self):
        left_rows = self._dataset("cre-id-1", "cre-id-2", "node-id-1")
        right_rows = self._dataset("cre-id-a", "cre-id-b", "node-id-a")
        right_rows["node"][0]["description"] = "Changed description"

        left = data_health.build_canonical_snapshot(left_rows)
        right = data_health.build_canonical_snapshot(right_rows)

        self.assertNotEqual(
            data_health.snapshot_digest(left), data_health.snapshot_digest(right)
        )
        diff = data_health.snapshot_diff(left, right)
        self.assertIn("node", diff)

    def test_raises_on_missing_foreign_key_target(self):
        rows = self._dataset("cre-id-1", "cre-id-2", "node-id-1")
        rows["cre_links"][0]["cre"] = "unknown-cre-id"

        with self.assertRaises(ValueError):
            data_health.build_canonical_snapshot(rows)


if __name__ == "__main__":
    unittest.main()
