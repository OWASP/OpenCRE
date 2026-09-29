"""Tests for shared OIE taxonomy index (from Node metadata, not static maps)."""

import unittest

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.oie_taxonomy import (
    TaxonomyIndex,
    set_default_taxonomy_index,
)


class TaxonomyIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.idx = fixture_taxonomy_index()
        set_default_taxonomy_index(self.idx)

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_exact_section_lookup(self) -> None:
        self.assertEqual(self.idx.lookup_section_id("a07"), ("authentication", "auth"))
        self.assertEqual(
            self.idx.lookup_section_id("LLM01"), ("prompt_injection", "ai")
        )
        self.assertIsNone(self.idx.lookup_section_id("V1.2.3"))

    def test_phrase_match(self) -> None:
        hit = self.idx.match_phrases("Encrypt data at rest with AES")
        self.assertEqual(hit, ("cryptography", "crypto"))

    def test_standard_hint(self) -> None:
        self.assertEqual(self.idx.family_for_standard("owasp_ccm_v4"), "cloud")

    def test_empty_index(self) -> None:
        empty = TaxonomyIndex.empty()
        self.assertIsNone(empty.lookup_section_id("A07"))
        self.assertIsNone(empty.match_phrases("prompt injection"))


if __name__ == "__main__":
    unittest.main()
