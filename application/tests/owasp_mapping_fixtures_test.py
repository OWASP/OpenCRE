import json
import re
import unittest
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "owasp_mappings"
EXPECTED_FIXTURES = {
    "owasp_aisvs_1_0.json",
    "owasp_api_top10_2023.json",
    "owasp_cheatsheets_supplement.json",
    "owasp_kubernetes_top10_2022.json",
    "owasp_kubernetes_top10_2025.json",
    "owasp_llm_top10_2025.json",
    "owasp_top10_2025.json",
}
CRE_ID_PATTERN = re.compile(r"^\d{3}-\d{3}$")


class TestOwaspMappingFixtures(unittest.TestCase):
    def test_fixture_set_is_complete(self) -> None:
        actual = {path.name for path in FIXTURE_DIR.glob("*.json")}
        self.assertEqual(actual, EXPECTED_FIXTURES)

    def test_fixtures_have_expected_mapping_shape(self) -> None:
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            with self.subTest(fixture=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))

                self.assertIsInstance(payload, list)
                self.assertGreater(len(payload), 0)

                for entry in payload:
                    self.assertIsInstance(entry, dict)
                    self.assertIsInstance(entry.get("section"), str)
                    self.assertTrue(entry["section"].strip())
                    self.assertIsInstance(entry.get("hyperlink"), str)
                    self.assertTrue(entry["hyperlink"].strip())
                    self.assertIn("cre_ids", entry)
                    self.assertIsInstance(entry["cre_ids"], list)
                    self.assertGreater(len(entry["cre_ids"]), 0)

                    if "section_id" in entry:
                        self.assertIsInstance(entry["section_id"], str)
                        self.assertTrue(entry["section_id"].strip())

                    for cre_id in entry["cre_ids"]:
                        self.assertIsInstance(cre_id, str)
                        self.assertTrue(cre_id.strip())
                        self.assertRegex(cre_id, CRE_ID_PATTERN)
