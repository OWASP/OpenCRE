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

                known_section_ids = {
                    entry["section_id"]
                    for entry in payload
                    if "section_id" in entry and isinstance(entry["section_id"], str)
                }
                seen_section_ids: set[str] = set()

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
                        self.assertNotIn(
                            entry["section_id"],
                            seen_section_ids,
                            msg=f"Duplicate section_id {entry['section_id']} in {path.name}",
                        )
                        seen_section_ids.add(entry["section_id"])

                    if "fallback_section_ids" in entry:
                        self.assertIsInstance(entry["fallback_section_ids"], list)
                        self.assertGreater(len(entry["fallback_section_ids"]), 0)
                        for fallback_section_id in entry["fallback_section_ids"]:
                            self.assertIsInstance(fallback_section_id, str)
                            self.assertTrue(fallback_section_id.strip())
                            self.assertIn(
                                fallback_section_id,
                                known_section_ids,
                                msg=(
                                    f"Fallback section id {fallback_section_id} "
                                    f"in {path.name} is not a known section_id"
                                ),
                            )

                    for cre_id in entry["cre_ids"]:
                        self.assertIsInstance(cre_id, str)
                        self.assertTrue(cre_id.strip())
                        self.assertRegex(cre_id, CRE_ID_PATTERN)
