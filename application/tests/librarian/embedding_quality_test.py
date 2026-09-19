"""Standard embedding quality rollup used by the audit script."""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.librarian.embedding_quality import (
    EmbeddingRow,
    classify_content,
    github_raw_content_url,
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
        self.assertEqual(
            usable_embedding_text("CRE name:foo description:"),
            "CRE name:foo description:",
        )

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

    def test_repr_standard_dump_is_not_prose(self) -> None:
        blob = (
            "Standard(name='PCI DSS', doctype=<Credoctypes.Standard: 'Standard'>, "
            "description='', links=[{'document': {'name': 'Cryptography'}}], "
            "id='PCI DSS:4.2:PAN')"
        )
        self.assertEqual(classify_content(blob), "repr")
        self.assertEqual(usable_embedding_text(blob), "")

    def test_repr_tool_dump_is_not_prose(self) -> None:
        blob = (
            "Tool(name='ZAP Rule', doctype=<Credoctypes.Tool: 'Tool'>, "
            "description='Do not trust client side input even if validated.', "
            "links=[], id='ZAP Rule:10010')"
        )
        self.assertEqual(classify_content(blob), "repr")

    def test_skip_to_content_without_navigation_menu_is_not_junk(self) -> None:
        body = (
            "skip to content owasp cheat sheet series threat modeling "
            "secrets management keep secrets out of source control and rotate "
            "them with a dedicated vault rather than environment files. "
        ) * 4
        self.assertEqual(classify_content(body), "prose")

    def test_usable_strips_github_nav_and_keeps_article_intro(self) -> None:
        chrome = (
            "skip to content navigation menu platform solutions resources "
            "open source enterprise pricing sign in sign up "
        ) * 3
        intro = (
            "Secrets Management Cheat Sheet Introduction Keep secrets out of git "
            "and provision them from a dedicated vault. "
        )
        later = (
            "Verify that the secret is still active before trusting it during "
            "break-glass restore of the secrets manager. "
        )
        used = usable_embedding_text(chrome + intro + later)
        self.assertNotIn("navigation menu", used.lower())
        self.assertIn("Keep secrets out of git", used)
        self.assertFalse(used.lower().startswith("verify that"))

    def test_github_raw_blob_and_tree_urls(self) -> None:
        self.assertEqual(
            github_raw_content_url(
                "https://github.com/OWASP/ASVS/blob/master/V2.md#v2-1-1"
            ),
            "https://raw.githubusercontent.com/OWASP/ASVS/master/V2.md",
        )
        self.assertEqual(
            github_raw_content_url(
                "https://github.com/OWASP/CheatSheetSeries/tree/master/"
                "cheatsheets/Secrets_Management_Cheat_Sheet.md"
            ),
            "https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/"
            "cheatsheets/Secrets_Management_Cheat_Sheet.md",
        )

    def test_github_raw_repo_home_uses_readme(self) -> None:
        self.assertEqual(
            github_raw_content_url("https://github.com/commjoen/wrongsecrets"),
            "https://github.com/commjoen/wrongsecrets/raw/HEAD/README.md",
        )


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

    def test_repr_family_is_flagged(self) -> None:
        blob = (
            "Standard(name='NIST 800-53 v5', doctype=<Credoctypes.Standard: "
            "'Standard'>, description='', links=[], id='NIST 800-53 v5:AC-2')"
        )
        rows = [EmbeddingRow(name="NIST 800-53 v5", content=blob)] * 5
        reports = {r.name: r for r in summarize_families(rows)}
        self.assertEqual(reports["NIST 800-53 v5"].verdict, "repr")
