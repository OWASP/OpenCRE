"""Standard embedding quality rollup used by the audit script."""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.librarian.embedding_quality import (
    EmbeddingRow,
    classify_content,
    summarize_families,
    usable_embedding_text,
)


class ClassifyContentTest(unittest.TestCase):
    def test_junk_frame_buster(self) -> None:
        self.assertEqual(
            classify_content(
                "you are viewing this page in an unauthorized frame window"
            ),
            "junk",
        )

    def test_stub_is_short(self) -> None:
        self.assertEqual(classify_content("CRE name:foo description:"), "stub")

    def test_junk_asvs_github_chrome(self) -> None:
        self.assertEqual(
            classify_content(
                "skip to content navigation menu platform solutions resources "
                "open source enterprise pricing sign in"
            ),
            "junk",
        )

    def test_junk_nist_official_website_chrome(self) -> None:
        self.assertEqual(
            classify_content(
                "an official website of the united states government here's how "
                "you know search search csrc menu"
            ),
            "junk",
        )

    def test_usable_text_extracts_verify_that_from_asvs_chrome(self) -> None:
        blob = (
            "skip to content navigation menu platform solutions resources "
            "open source enterprise pricing sign in " * 4
            + "Verify that passwords are at least 12 characters in length and "
            "that the application rejects common passwords from a dictionary."
        )
        used = usable_embedding_text(blob)
        self.assertTrue(used.lower().startswith("verify that"))
        self.assertIn("12 characters", used)

    def test_usable_text_empty_when_chrome_has_no_requirement(self) -> None:
        self.assertEqual(
            usable_embedding_text(
                "you are viewing this page in an unauthorized frame window"
            ),
            "",
        )

    def test_prose(self) -> None:
        body = (
            "The organization manages information system accounts, including "
            "establishing, activating, modifying, disabling, and removing accounts. "
        ) * 8
        self.assertEqual(classify_content(body), "prose")

    def test_usable_text_prose_unchanged(self) -> None:
        body = (
            "The organization manages information system accounts, including "
            "establishing, activating, modifying, disabling, and removing accounts. "
        ) * 8
        self.assertEqual(usable_embedding_text(body), body.strip())


class SummarizeFamiliesTest(unittest.TestCase):
    def test_duplicate_identical_blobs_are_flagged(self) -> None:
        blob = "you are viewing this page in an unauthorized frame window " * 20
        rows = [
            EmbeddingRow(name="NIST 800-53 v5", content=blob),
            EmbeddingRow(name="NIST 800-53 v5", content=blob),
            EmbeddingRow(
                name="PCI DSS", content=("Protect stored PAN with hashing. " * 20)
            ),
        ]
        reports = {r.name: r for r in summarize_families(rows)}
        self.assertEqual(reports["NIST 800-53 v5"].verdict, "junk")
        self.assertLessEqual(reports["NIST 800-53 v5"].unique_ratio, 0.5)
        self.assertEqual(reports["PCI DSS"].verdict, "prose")
