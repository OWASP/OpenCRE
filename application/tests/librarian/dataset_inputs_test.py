"""Integrity tests for the fixture inputs used to build the golden dataset."""

import json
import os
import unittest

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_INPUTS = os.path.join(_HERE, "fixtures", "dataset_inputs")
_SUPPLEMENT = os.path.join(
    _REPO_ROOT,
    "application",
    "tests",
    "fixtures",
    "owasp_mappings",
    "owasp_cheatsheets_supplement.json",
)


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestDatasetInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_nodes = _load(os.path.join(_INPUTS, "source_nodes.json"))
        cls.curated = _load(os.path.join(_INPUTS, "curated.json"))
        cls.manifest = _load(os.path.join(_INPUTS, "manifest.json"))
        cls.supplement = _load(_SUPPLEMENT)

    def test_source_nodes_have_required_fields(self):
        required = {"standard", "name", "section_id", "section", "cre_ids"}

        for index, node in enumerate(self.source_nodes):
            with self.subTest(index=index):
                self.assertTrue(required.issubset(node))
                for field in ("standard", "name", "section_id"):
                    self.assertIsInstance(node[field], str)
                    self.assertTrue(node[field].strip(), field)

                self.assertIsInstance(node["section"], str)
                self.assertIsInstance(node["cre_ids"], list)
                self.assertTrue(node["cre_ids"])
                self.assertTrue(
                    all(
                        isinstance(cre_id, str) and cre_id for cre_id in node["cre_ids"]
                    )
                )

    def test_source_node_keys_are_unique(self):
        keys = [
            (node["standard"], node["name"], node["section_id"])
            for node in self.source_nodes
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_cre_ids_are_sorted_and_deduplicated(self):
        for node in self.source_nodes:
            with self.subTest(standard=node["standard"], section_id=node["section_id"]):
                cre_ids = node["cre_ids"]
                self.assertEqual(cre_ids, sorted(set(cre_ids)))

    def test_curated_sections_and_fields_exist(self):
        expected_sections = {
            "explicit",
            "update",
            "ambiguous",
            "cheatsheet_fixtures",
            "multilink_pins",
        }
        self.assertEqual(set(self.curated), expected_sections)

        required_fields = {
            "explicit": {"id", "asvs_section_id", "text_template", "title_hint"},
            "update": {"id", "asvs_section_id", "text", "prior_text"},
            "ambiguous": {"id", "text", "reason_code"},
            "cheatsheet_fixtures": {
                "id",
                "section",
                "text",
                "title_hint",
                "section_path",
            },
            "multilink_pins": {"name", "section_id"},
        }

        for section, records in self.curated.items():
            self.assertIsInstance(records, list)
            for index, record in enumerate(records):
                with self.subTest(section=section, index=index):
                    self.assertTrue(required_fields[section].issubset(record))

    def test_multilink_pins_resolve_to_two_to_four_cre_ids(self):
        nodes_by_key = {
            (node["name"], node["section_id"]): node for node in self.source_nodes
        }

        pin_keys = [
            (pin["name"], pin["section_id"]) for pin in self.curated["multilink_pins"]
        ]
        self.assertEqual(len(pin_keys), len(set(pin_keys)))

        for key in pin_keys:
            with self.subTest(pin=key):
                self.assertIn(key, nodes_by_key)
                cre_ids = nodes_by_key[key]["cre_ids"]
                self.assertGreaterEqual(len(cre_ids), 2)
                self.assertLessEqual(len(cre_ids), 4)

    def test_cheatsheet_fixtures_have_supplement_mappings(self):
        mapped_sections = {
            entry["section"] for entry in self.supplement if entry.get("cre_ids")
        }

        for fixture in self.curated["cheatsheet_fixtures"]:
            with self.subTest(section=fixture["section"]):
                self.assertIn(fixture["section"], mapped_sections)

    def test_manifest_counts_match_fixture_contents(self):
        counts = self.manifest["record_counts"]

        expected = {
            "source_nodes": len(self.source_nodes),
            "asvs": sum(node["standard"] == "ASVS" for node in self.source_nodes),
            "cwe_multilink": sum(
                node["standard"] == "CWE" for node in self.source_nodes
            ),
            "explicit": len(self.curated["explicit"]),
            "update": len(self.curated["update"]),
            "ambiguous": len(self.curated["ambiguous"]),
            "cheatsheet_fixtures": len(self.curated["cheatsheet_fixtures"]),
            "multilink_pins": len(self.curated["multilink_pins"]),
        }

        self.assertEqual(counts, expected)
        self.assertEqual(self.manifest["schema_version"], "0.1.0")
        self.assertTrue(self.manifest["refreshed_at"])
        self.assertTrue(self.manifest["source"])


if __name__ == "__main__":
    unittest.main()
