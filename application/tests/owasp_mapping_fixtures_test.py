from cre_logging import get_logger

logger = get_logger(__name__)

import re
import unittest

from application.utils import mapping_fixtures


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
        self.assertEqual(
            set(mapping_fixtures.list_owasp_mapping_fixtures()), EXPECTED_FIXTURES
        )

    def test_load_all_returns_every_named_fixture(self) -> None:
        loaded = mapping_fixtures.load_all_owasp_mapping_fixtures()
        self.assertEqual(set(loaded), EXPECTED_FIXTURES)
        for filename, payload in loaded.items():
            with self.subTest(fixture=filename):
                self.assertIsInstance(payload, list)
                self.assertGreater(len(payload), 0)

    def test_load_accepts_stem_without_json_suffix(self) -> None:
        by_stem = mapping_fixtures.load_owasp_mapping_fixture("owasp_top10_2025")
        by_name = mapping_fixtures.load_owasp_mapping_fixture("owasp_top10_2025.json")
        self.assertEqual(by_stem, by_name)

    def test_load_unknown_fixture_raises(self) -> None:
        with self.assertRaises(FileNotFoundError) as ctx:
            mapping_fixtures.load_owasp_mapping_fixture("not_a_real_mapping")
        self.assertIn("not_a_real_mapping.json", str(ctx.exception))

    def test_k8s_2025_uses_per_item_owasp_hyperlinks(self) -> None:
        # Data from #953 (Bornunique911): section pages, not the family homepage.
        entries = mapping_fixtures.load_owasp_mapping_fixture(
            "owasp_kubernetes_top10_2025"
        )
        self.assertEqual(10, len(entries))
        self.assertEqual("K01", entries[0]["section_id"])
        self.assertIn("/2025/en/src/K01-", entries[0]["hyperlink"])
        self.assertEqual(["233-748", "486-813"], entries[0]["cre_ids"])

    def test_resolved_cre_ids_follow_fallback_when_own_ids_empty(self) -> None:
        by_id = {
            "K05": {"cre_ids": ["148-420"]},
            "K10": {
                "cre_ids": [],
                "fallback_section_ids": ["K05"],
            },
        }
        self.assertEqual(
            ["148-420"],
            mapping_fixtures.resolved_cre_ids(by_id["K10"], by_id),
        )

    def test_fixtures_have_expected_mapping_shape(self) -> None:
        loaded = mapping_fixtures.load_all_owasp_mapping_fixtures()
        for filename, payload in loaded.items():
            with self.subTest(fixture=filename):

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
                            msg=f"Duplicate section_id {entry['section_id']} in {filename}",
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
                                    f"in {filename} is not a known section_id"
                                ),
                            )

                    for cre_id in entry["cre_ids"]:
                        self.assertIsInstance(cre_id, str)
                        self.assertTrue(cre_id.strip())
                        self.assertRegex(cre_id, CRE_ID_PATTERN)
