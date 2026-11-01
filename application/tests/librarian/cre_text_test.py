"""Short CRE embedding / CE pair text from name + linked standard titles."""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.librarian.cre_text import (
    LinkedStandardRef,
    build_cre_embedding_text,
    enrich_cre_contents,
)


class BuildCreEmbeddingTextTest(unittest.TestCase):
    def test_stub_when_no_links_or_description(self) -> None:
        text = build_cre_embedding_text(
            name="Access Control",
            description="",
            cre_id="481-710",
            linked=(),
        )
        self.assertIn("name:Access Control", text)
        self.assertIn("id:481-710", text)
        self.assertNotIn("linked:", text)

    def test_appends_capped_linked_titles_not_page_dumps(self) -> None:
        linked = (
            LinkedStandardRef("NIST 800-53 v5", "AC-2", "Account Management"),
            LinkedStandardRef("ASVS", "V2.1.1", "Password length"),
        )
        text = build_cre_embedding_text(
            name="Access Control",
            description="",
            cre_id="481-710",
            linked=linked,
            include_linked_titles=True,
            max_linked_chars=80,
        )
        self.assertIn("NIST 800-53 v5 AC-2 Account Management", text)
        self.assertIn("description:", text)
        self.assertLess(len(text), 400)
        self.assertNotIn("skip to content", text)

    def test_enrich_only_extends_stub_contents(self) -> None:
        contents = {
            "cre-a": "Credoctypes.CRE name:Access Control description: id:1",
            "cre-b": "already long prose " * 40,
        }
        refs = {
            "cre-a": [LinkedStandardRef("PCI DSS", "3.4", "Stored PAN")],
        }
        out = enrich_cre_contents(contents, refs, names={"cre-a": "Access Control"})
        self.assertIn("PCI DSS 3.4", out["cre-a"])
        self.assertEqual(out["cre-b"], contents["cre-b"])

    def test_existing_description_keeps_linked_prose_separate(self) -> None:
        text = build_cre_embedding_text(
            name="Access Control",
            description="Existing CRE prose about access control.",
            cre_id="481-710",
            linked=(
                LinkedStandardRef(
                    "PCI DSS",
                    "3.4",
                    "Stored PAN",
                    prose=(
                        "Render PAN unreadable anywhere it is stored by using "
                        "strong cryptography, truncation, or index tokens."
                    ),
                ),
            ),
            include_linked_titles=True,
        )
        self.assertIn("description:Existing CRE prose about access control.", text)
        self.assertIn("linked:", text)
        self.assertIn("Render PAN unreadable", text)

    def test_match_text_prefers_embeddings_content_over_title(self) -> None:
        ref = LinkedStandardRef(
            "PCI DSS",
            "3.4",
            "Stored PAN",
            prose=(
                "Render PAN unreadable anywhere it is stored by using strong "
                "cryptography, truncation, index tokens, or one-way hashes."
            ),
        )
        self.assertIn("Render PAN unreadable", ref.match_text())
        self.assertNotEqual(ref.match_text(), ref.line())

    def test_match_text_skips_junk_chrome_and_falls_back_to_title(self) -> None:
        ref = LinkedStandardRef(
            "NIST 800-53 v5",
            "AC-2",
            "Account Management",
            prose=(
                "unauthorized frame window You have JavaScript disabled. "
                "This is a potential security issue, you are being redirected."
            ),
        )
        self.assertEqual(ref.match_text(), ref.line())

    def test_match_text_extracts_buried_asvs_requirement(self) -> None:
        ref = LinkedStandardRef(
            "ASVS",
            "V2.1.1",
            "Password length",
            prose=(
                "skip to content navigation menu platform solutions resources "
                "open source " * 6
                + "Verify that passwords are at least 12 characters in length "
                "and that the application rejects common passwords from a dictionary."
            ),
        )
        self.assertIn("Verify that passwords are at least 12", ref.match_text())
        self.assertNotIn("skip to content", ref.match_text())

    def test_enrich_uses_linked_embeddings_content_as_description(self) -> None:
        pci_prose = (
            "Requirement 3.4: Render PAN unreadable anywhere it is stored "
            "by using strong cryptography. " * 8
        )
        contents = {
            "cre-a": "CRE\n name:Stored Account Data\n description:\n id:cre-a",
        }
        refs = {
            "cre-a": [
                LinkedStandardRef("PCI DSS", "3.4", "Stored PAN", prose=pci_prose),
                LinkedStandardRef(
                    "NIST 800-53 v5",
                    "AC-2",
                    "Account Management",
                    prose="unauthorized frame window you have javascript disabled",
                ),
            ],
        }
        out = enrich_cre_contents(
            contents, refs, names={"cre-a": "Stored Account Data"}
        )
        self.assertIn("Render PAN unreadable", out["cre-a"])
        self.assertIn("description:", out["cre-a"])
        self.assertNotIn("unauthorized frame window", out["cre-a"])
        self.assertIn("NIST 800-53 v5 AC-2 Account Management", out["cre-a"])
        self.assertLessEqual(len(out["cre-a"]), 4000)
