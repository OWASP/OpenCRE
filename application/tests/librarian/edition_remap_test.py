"""Tests for edition remap (heuristic + validation + transfer service)."""

import unittest
from typing import List

from application.utils.librarian.edition_remap import (
    EditionRemapCache,
    EditionSection,
    EditionTransferService,
    StandardEdition,
    family_and_year,
    heuristic_remap,
    parse_chunk_standard,
    propose_remap,
    validate_remap,
)


class FamilyParseTest(unittest.TestCase):
    def test_top10_node_name(self) -> None:
        self.assertEqual(family_and_year("OWASP Top 10 2021"), ("owasp_top10", 2021))

    def test_standard_line_filename(self) -> None:
        text = (
            "Standard: owasp_top10_2025.json\n"
            "Source: A04.txt\n"
            "Section-ID: A04\n"
            "Section: Cryptographic Failures\n"
        )
        self.assertEqual(parse_chunk_standard(text), ("owasp_top10", 2025, "A04"))

    def test_version_line_with_standard_name(self) -> None:
        text = (
            "Standard: OWASP Top 10\n"
            "Version: 2025\n"
            "Source: A01.txt\n"
            "Section-ID: A01\n"
        )
        self.assertEqual(parse_chunk_standard(text), ("owasp_top10", 2025, "A01"))


class HeuristicRemapTest(unittest.TestCase):
    def test_title_reshape_crypto(self) -> None:
        new = [
            EditionSection("A04", "Cryptographic Failures"),
            EditionSection("A02", "Security Misconfiguration"),
        ]
        old = [
            EditionSection("A02", "Cryptographic Failures"),
            EditionSection("A05", "Security Misconfiguration"),
        ]
        remap = heuristic_remap(new, old)
        self.assertEqual(remap["A04"], ["A02"])
        self.assertEqual(remap["A02"], ["A05"])


class ProposeRemapTest(unittest.TestCase):
    def test_llm_stub_validated(self) -> None:
        new = [EditionSection("A04", "Cryptographic Failures")]
        old = [
            EditionSection("A02", "Cryptographic Failures"),
            EditionSection("A99", "Bogus"),
        ]

        def llm(system: str, user: str) -> str:
            return '{"A04": ["A02", "NOPE"], "ZZZ": ["A02"]}'

        remap = propose_remap(
            family="owasp_top10",
            new_year=2025,
            old_year=2021,
            new_sections=new,
            old_sections=old,
            llm_fn=llm,
        )
        self.assertEqual(remap["A04"], ["A02"])
        self.assertNotIn("ZZZ", remap)


class TransferServiceTest(unittest.TestCase):
    def test_inherits_predecessor_cres(self) -> None:
        old = StandardEdition(
            family="owasp_top10",
            year=2021,
            label="OWASP Top 10 2021",
            sections=(
                EditionSection("A02", "Cryptographic Failures"),
                EditionSection("A05", "Security Misconfiguration"),
            ),
        )
        new = StandardEdition(
            family="owasp_top10",
            year=2025,
            label="OWASP Top 10 2025",
            sections=(
                EditionSection("A04", "Cryptographic Failures"),
                EditionSection("A02", "Security Misconfiguration"),
            ),
        )
        section_cres = {
            ("owasp_top10", 2021, "A02"): {"cre-crypto"},
            ("owasp_top10", 2021, "A05"): {"cre-config"},
        }
        svc = EditionTransferService(
            editions=[old, new],
            section_cre_ids=section_cres,
            llm_fn=None,  # heuristic
            cache=EditionRemapCache(memory={}),
            low_result_max=2,
        )
        ids = svc.cre_ids_for_new_section("owasp_top10", 2025, "A04")
        self.assertEqual(ids, {"cre-crypto"})
        expanded = svc.expand_allowlist_if_low(
            "Standard: owasp_top10_2025.json\nSource: A04.txt\nSection-ID: A04\n",
            frozenset({"other"}),
            candidate_count=0,
        )
        self.assertIn("cre-crypto", expanded)
        self.assertIn("other", expanded)


if __name__ == "__main__":
    unittest.main()
