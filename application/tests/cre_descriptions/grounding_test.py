"""Grounding helpers for one-shot CRE description generation."""

import unittest

from application.utils.cre_descriptions.grounding import (
    grounding_snippet,
    usable_grounding_leaves,
)


def _nist_chrome() -> str:
    return (
        "An official website of the United States government "
        "Here's how you know skip to content navigation menu "
        "unauthorized frame window You have JavaScript disabled. "
        "This is a potential security issue, you are being redirected."
    )


def _zap_junk() -> str:
    return (
        "unauthorized frame window You have JavaScript disabled. "
        "This is a potential security issue, you are being redirected. "
        "ZAP HUD loading"
    )


def _pci_prose() -> str:
    return (
        "Requirement 3.4: Render PAN unreadable anywhere it is stored "
        "by using strong cryptography, truncation, or index tokens so that "
        "a compromise of one store does not expose the full primary account number."
    )


class UsableGroundingLeavesTest(unittest.TestCase):
    def test_skips_nist_chrome_and_zap_junk(self) -> None:
        leaves = usable_grounding_leaves([_nist_chrome(), _zap_junk(), _pci_prose()])
        self.assertEqual(len(leaves), 1)
        self.assertIn("Render PAN unreadable", leaves[0])
        blob = " ".join(leaves).lower()
        self.assertNotIn("united states government", blob)
        self.assertNotIn("javascript disabled", blob)

    def test_skips_empty_and_stub(self) -> None:
        leaves = usable_grounding_leaves(["", "   ", "short", _pci_prose()])
        self.assertEqual(len(leaves), 1)
        self.assertIn("Render PAN", leaves[0])


class GroundingSnippetTest(unittest.TestCase):
    def test_includes_leaves_and_neighbours(self) -> None:
        snippet = grounding_snippet(
            [_pci_prose()],
            ["Session binding", "Token storage"],
            max_chars=500,
        )
        self.assertIn("Render PAN", snippet)
        self.assertIn("Session binding", snippet)
        self.assertIn("Token storage", snippet)

    def test_respects_max_chars(self) -> None:
        long_leaf = "A" * 1000
        snippet = grounding_snippet([long_leaf], [], max_chars=80)
        self.assertLessEqual(len(snippet), 80)


if __name__ == "__main__":
    unittest.main()
