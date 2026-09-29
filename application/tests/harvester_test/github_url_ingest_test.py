"""Unit tests for point-and-shoot GitHub URL ingest helpers."""

from __future__ import annotations

import unittest

from application.utils.harvester.github_url_ingest import (
    format_knowledge_item,
    parse_github_url,
)


class ParseGitHubUrlTests(unittest.TestCase):
    def test_owner_repo(self) -> None:
        p = parse_github_url("https://github.com/OWASP/ASVS")
        self.assertEqual(p.owner, "OWASP")
        self.assertEqual(p.repo, "ASVS")
        self.assertIsNone(p.branch)
        self.assertIsNone(p.path_prefix)

    def test_git_suffix_and_www(self) -> None:
        p = parse_github_url("https://www.github.com/OWASP/ASVS.git")
        self.assertEqual(p.owner, "OWASP")
        self.assertEqual(p.repo, "ASVS")

    def test_tree_branch_and_path(self) -> None:
        p = parse_github_url("https://github.com/OWASP/ASVS/tree/master/5.0/en")
        self.assertEqual(p.branch, "master")
        self.assertEqual(p.path_prefix, "5.0/en")

    def test_rejects_non_github(self) -> None:
        with self.assertRaises(ValueError):
            parse_github_url("https://gitlab.com/OWASP/ASVS")


class FormatKnowledgeItemTests(unittest.TestCase):
    def test_includes_path_and_label(self) -> None:
        out = format_knowledge_item(
            path="5.0/en/V1.md",
            label="KNOWLEDGE",
            confidence=0.91,
            text="Verify that input is sanitized.",
            reasoning="looks like a control",
        )
        self.assertIn("path: 5.0/en/V1.md", out)
        self.assertIn("label: KNOWLEDGE", out)
        self.assertIn("Verify that input is sanitized.", out)


if __name__ == "__main__":
    unittest.main()
