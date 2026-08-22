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
EXPECTED_SECTION_COUNTS = {
    "owasp_aisvs_1_0.json": 14,
    "owasp_api_top10_2023.json": 10,
    "owasp_cheatsheets_supplement.json": 9,
    "owasp_kubernetes_top10_2022.json": 10,
    "owasp_kubernetes_top10_2025.json": 10,
    "owasp_llm_top10_2025.json": 10,
    "owasp_top10_2025.json": 10,
}
EXPECTED_LINK_PREFIXES = {
    "owasp_aisvs_1_0.json": ("https://github.com/OWASP/AISVS/tree/main/1.0/en/",),
    "owasp_api_top10_2023.json": ("https://owasp.org/API-Security/editions/2023/en/",),
    "owasp_cheatsheets_supplement.json": (
        "https://cheatsheetseries.owasp.org/cheatsheets/",
    ),
    "owasp_kubernetes_top10_2022.json": (
        "https://owasp.org/www-project-kubernetes-top-ten/2022/en/src/",
    ),
    "owasp_kubernetes_top10_2025.json": (
        "https://owasp.org/www-project-kubernetes-top-ten/2025/en/src/",
    ),
    "owasp_llm_top10_2025.json": ("https://genai.owasp.org/llmrisk/",),
    "owasp_top10_2025.json": ("https://owasp.org/Top10/2025/",),
}
EXPECTED_GOLDEN_MAPPINGS = {
    ("owasp_api_top10_2023.json", "API7"): {
        "section": "Server Side Request Forgery",
        "cre_ids": ["028-728", "657-084"],
    },
    ("owasp_kubernetes_top10_2025.json", "K01"): {
        "section": "Insecure Workload Configurations",
        "cre_ids": ["233-748", "486-813"],
        "fallback_section_ids": None,
    },
    ("owasp_kubernetes_top10_2025.json", "K04"): {
        "section": "Lack Of Cluster Level Policy Enforcement",
        "cre_ids": ["117-371"],
        "fallback_section_ids": None,
    },
    ("owasp_kubernetes_top10_2025.json", "K07"): {
        "section": "Misconfigured And Vulnerable Cluster Components",
        "cre_ids": ["053-751", "233-748", "486-813", "715-334"],
        "fallback_section_ids": ["K09", "K10"],
    },
    ("owasp_llm_top10_2025.json", "LLM01"): {
        "section": "Prompt Injection",
        "cre_ids": ["161-451", "760-764"],
    },
    ("owasp_top10_2025.json", "A05"): {
        "section": "Injection",
        "cre_ids": ["031-447", "064-808", "760-764"],
    },
}
EXPECTED_CROSS_FIXTURE_LINKS = {
    ("owasp_cheatsheets_supplement.json", "Kubernetes Security Cheat Sheet"): {
        "cre_ids": ["467-784", "233-748", "486-813"],
    },
    ("owasp_aisvs_1_0.json", "AISVS10"): {
        "cre_ids": ["307-507", "715-223"],
    },
}


class TestOwaspMappingFixtures(unittest.TestCase):
    @staticmethod
    def _load_fixture(path: Path) -> list[dict[str, object]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise AssertionError(f"{path.name} must contain a top-level list")
        return payload

    def test_fixture_set_is_complete(self) -> None:
        actual = {path.name for path in FIXTURE_DIR.glob("*.json")}
        self.assertEqual(actual, EXPECTED_FIXTURES)

    def test_fixtures_have_expected_mapping_shape(self) -> None:
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            with self.subTest(fixture=path.name):
                payload = self._load_fixture(path)
                self.assertGreater(len(payload), 0)
                self.assertEqual(EXPECTED_SECTION_COUNTS[path.name], len(payload))

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
                    self.assertTrue(
                        entry["hyperlink"].startswith(
                            EXPECTED_LINK_PREFIXES[path.name]
                        ),
                        msg=(
                            f"Unexpected hyperlink prefix for {path.name}: "
                            f"{entry['hyperlink']}"
                        ),
                    )
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

    def test_expected_golden_mappings_remain_stable(self) -> None:
        for (fixture_name, section_key), expected in EXPECTED_GOLDEN_MAPPINGS.items():
            path = FIXTURE_DIR / fixture_name
            payload = self._load_fixture(path)
            entry = next(
                entry for entry in payload if entry.get("section_id") == section_key
            )
            with self.subTest(fixture=fixture_name, section_id=section_key):
                self.assertEqual(expected["section"], entry["section"])
                self.assertEqual(expected["cre_ids"], entry["cre_ids"])
                if "fallback_section_ids" in expected:
                    self.assertEqual(
                        expected["fallback_section_ids"],
                        entry.get("fallback_section_ids"),
                    )

    def test_cross_fixture_reference_rows_stay_reviewable(self) -> None:
        for (fixture_name, key), expected in EXPECTED_CROSS_FIXTURE_LINKS.items():
            path = FIXTURE_DIR / fixture_name
            payload = self._load_fixture(path)
            if key.startswith("AISVS"):
                entry = next(
                    entry for entry in payload if entry.get("section_id") == key
                )
            else:
                entry = next(entry for entry in payload if entry.get("section") == key)
            with self.subTest(fixture=fixture_name, key=key):
                self.assertEqual(expected["cre_ids"], entry["cre_ids"])

    def test_known_ambiguous_kubernetes_mapping_is_explicit(self) -> None:
        payload = self._load_fixture(FIXTURE_DIR / "owasp_kubernetes_top10_2022.json")
        entries_by_section_id = {
            entry["section_id"]: entry
            for entry in payload
            if isinstance(entry.get("section_id"), str)
        }
        # K01/K09 intentionally share configuration-focused CREs until a better
        # K09-specific mapping is validated from upstream source material.
        self.assertEqual(
            entries_by_section_id["K01"]["cre_ids"],
            entries_by_section_id["K09"]["cre_ids"],
        )
