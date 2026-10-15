"""Tests for ingestion-derived project aliases."""

from __future__ import annotations

import unittest

from application.utils.owasp_agent.project_aliases import derive_project_aliases
from application.utils.owasp_agent.queries import _match_project


class TestDeriveProjectAliases(unittest.TestCase):
    def test_ai_exchange_from_title_tags_and_host(self) -> None:
        aliases = derive_project_aliases(
            "OWASP AI Exchange",
            key="ai-security-and-privacy-guide",
            tags=["AIsecpri", "AI", "security", "privacy"],
            url="https://owaspai.org/docs/",
            description="Find material on the OWASP AI Exchange website",
        )
        low = {a.lower() for a in aliases}
        self.assertIn("ai exchange", low)
        self.assertTrue("owaspai" in low or "aisecpri" in low)

    def test_genai_from_tags(self) -> None:
        aliases = derive_project_aliases(
            "OWASP Top 10 for Large Language Model Applications",
            key="top-10-for-large-language-model-applications",
            tags=["llm", "genai"],
            description="Active development moved to GenAI Security Project at genai.owasp.org",
            url="https://genai.owasp.org/",
        )
        low = {a.lower() for a in aliases}
        self.assertIn("genai", low)
        self.assertIn("llm", low)


class TestMatchProjectAliases(unittest.TestCase):
    def test_match_via_ingested_alias(self) -> None:
        projects = [
            {
                "key": "ai-security-and-privacy-guide",
                "name": "OWASP AI Exchange",
                "description": "AI security guidance",
                "tags": ["ai", "privacy"],
                "aliases": ["ai exchange", "owaspai", "aiexchange"],
                "url": "https://owaspai.org/",
            }
        ]
        hit = _match_project(projects, "AI Exchange")
        self.assertIsNotNone(hit)
        hit2 = _match_project(projects, "owaspai")
        self.assertIsNotNone(hit2)


if __name__ == "__main__":
    unittest.main()
