"""Tests for the C.0.5 deterministic explicit-CRE fast path.

Covers extraction (pattern boundaries, ordering, dedup) and resolution
(the fail-safe rule: only a single known reference auto-links; unknown or
conflicting references must fall through to review).
"""

import unittest

from application.utils.librarian.explicit_link_resolver import (
    Resolution,
    ResolutionOutcome,
    extract_cre_refs,
    resolve,
)

KNOWN = {"027-555", "123-456", "764-507"}


class ExtractCreRefsTest(unittest.TestCase):
    def test_extraction_table(self) -> None:
        cases = [
            ("plain reference", "Per CRE 027-555, verify passwords.", ["027-555"]),
            (
                "inside an opencre url",
                "See https://opencre.org/cre/123-456 for details.",
                ["123-456"],
            ),
            (
                "multiple distinct, in order",
                "Maps to 123-456 and also 027-555.",
                ["123-456", "027-555"],
            ),
            ("repeated reference deduped", "027-555 then 027-555 again.", ["027-555"]),
            ("no reference", "Use MFA for all administrative access.", []),
            ("too many leading digits", "CVE-2024-1234-567 is unrelated.", []),
            ("too many trailing digits", "Item 027-5555 is not a CRE id.", []),
            ("punctuation boundary", "(see CRE 764-507).", ["764-507"]),
        ]
        for name, text, expected in cases:
            with self.subTest(name):
                self.assertEqual(extract_cre_refs(text), expected)


class ResolveTest(unittest.TestCase):
    def test_single_known_reference_resolves(self) -> None:
        resolution = resolve("Per CRE 027-555, verify passwords.", KNOWN)
        self.assertEqual(
            resolution,
            Resolution(ResolutionOutcome.resolved, ("027-555",), ()),
        )

    def test_no_reference_falls_through_to_semantic_path(self) -> None:
        resolution = resolve("Use MFA for all administrative access.", KNOWN)
        self.assertEqual(resolution.outcome, ResolutionOutcome.no_reference)
        self.assertEqual(resolution.cre_ids, ())

    def test_unknown_reference_never_auto_links(self) -> None:
        resolution = resolve("Per CRE 999-999, do the thing.", KNOWN)
        self.assertEqual(resolution.outcome, ResolutionOutcome.unknown_reference)
        self.assertEqual(resolution.cre_ids, ())
        self.assertEqual(resolution.unknown_refs, ("999-999",))

    def test_mixed_known_and_unknown_routes_to_review(self) -> None:
        resolution = resolve("Maps to 027-555 and 999-999.", KNOWN)
        self.assertEqual(resolution.outcome, ResolutionOutcome.unknown_reference)
        # The known id survives as a review suggestion, but must not auto-link.
        self.assertEqual(resolution.cre_ids, ("027-555",))
        self.assertEqual(resolution.unknown_refs, ("999-999",))

    def test_conflicting_known_references_route_to_review(self) -> None:
        resolution = resolve("Maps to 123-456 and also 027-555.", KNOWN)
        self.assertEqual(resolution.outcome, ResolutionOutcome.conflicting_references)
        self.assertEqual(resolution.cre_ids, ("123-456", "027-555"))

    def test_repeated_single_reference_still_resolves(self) -> None:
        resolution = resolve("027-555 is cited twice: 027-555.", KNOWN)
        self.assertEqual(resolution.outcome, ResolutionOutcome.resolved)
        self.assertEqual(resolution.cre_ids, ("027-555",))


if __name__ == "__main__":
    unittest.main()
