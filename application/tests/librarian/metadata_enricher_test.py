"""Tests for LLM metadata enrichment service helpers."""

import unittest

from application.utils.librarian.metadata_enricher import (
    match_text_blob,
    merge_oie_enrichment,
    parse_enrichment_json,
)


class ParseEnrichmentJsonTest(unittest.TestCase):
    def test_fenced_json(self) -> None:
        raw = '```json\n{"summary": "hello", "aliases": ["a"]}\n```'
        data = parse_enrichment_json(raw)
        self.assertEqual(data["summary"], "hello")
        self.assertEqual(data["aliases"], ["a"])


class MergeOieEnrichmentTest(unittest.TestCase):
    def test_merges_and_sets_version(self) -> None:
        merged = merge_oie_enrichment(
            {"phrases": ["old"], "family": "access"},
            {
                "summary": "Verbose summary about RBAC.",
                "aliases": ["rbac", "overly permissive authorization"],
                "related_topics": ["kubernetes authorization"],
                "applies_to": ["kubernetes", "api"],
                "transfer_hints": ["owasp_k8s_top10"],
                "anti_topics": ["prompt injection"],
            },
            section_title="Identity & Access Management",
        )
        self.assertEqual(merged["summary"], "Verbose summary about RBAC.")
        self.assertIn("rbac", merged["aliases"])
        self.assertIn("old", merged["phrases"])
        self.assertEqual(merged["section_title"], "Identity & Access Management")
        self.assertEqual(merged["enrichment_version"], 3)
        blob = match_text_blob(merged)
        self.assertIn("Verbose summary", blob)
        self.assertIn("kubernetes authorization", blob)


if __name__ == "__main__":
    unittest.main()
