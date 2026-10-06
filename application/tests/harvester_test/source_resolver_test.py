from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.harvester.dest_classifier import classify_github_repo
from application.utils.harvester.github_sources import parse_github_source
from application.utils.harvester.schemas import ReposFile
from application.utils.harvester.source_resolver import resolve_sources


class GithubSourceParseTests(unittest.TestCase):
    def test_org_url_and_shorthand(self) -> None:
        from_url = parse_github_source("https://github.com/OWASP/")
        self.assertEqual(from_url.canonical, "github.com/OWASP/")
        self.assertTrue(from_url.is_org)
        self.assertEqual(parse_github_source("OWASP").canonical, "github.com/OWASP/")

    def test_repo_url(self) -> None:
        parsed = parse_github_source("github.com/OWASP/ASVS")
        self.assertEqual(parsed.canonical, "github.com/OWASP/ASVS")
        self.assertEqual(parsed.repo, "ASVS")
        self.assertFalse(parsed.is_org)

    def test_rejects_injection(self) -> None:
        for raw in ("OWASP?x=1", "github.com/OWASP#frag", ".."):
            with self.assertRaises(ValueError):
                parse_github_source(raw)


class DestClassifierTests(unittest.TestCase):
    def test_asvs_and_cheatsheet_are_opencre(self) -> None:
        self.assertEqual(classify_github_repo(repo="ASVS"), "opencre")
        self.assertEqual(
            classify_github_repo(repo="CheatSheetSeries"),
            "opencre",
        )

    def test_code_project_is_agent(self) -> None:
        self.assertEqual(
            classify_github_repo(
                repo="NestJS-starter",
                language="TypeScript",
                description="A web API",
            ),
            "agent",
        )

    def test_explicit_override(self) -> None:
        self.assertEqual(
            classify_github_repo(repo="random-tool", explicit_opencre=True),
            "opencre",
        )


class SourceResolverTests(unittest.TestCase):
    def test_org_source_classifies_without_writing_every_repo_into_config(
        self,
    ) -> None:
        repos_file = ReposFile.model_validate(
            {
                "sources": ["github.com/OWASP/"],
                "repositories": [
                    {
                        "id": "owasp-asvs",
                        "type": "github",
                        "owner": "OWASP",
                        "repo": "ASVS",
                        "paths": {"include": ["**/*.md"]},
                        "chunking": {
                            "strategy": "markdown_heading",
                            "max_tokens": 1200,
                        },
                        "polling": {"mode": "incremental", "interval_minutes": 60},
                    }
                ],
            }
        )

        def list_owner(owner: str):
            self.assertEqual(owner, "OWASP")
            return [
                {"name": "ASVS", "fork": False, "archived": False, "language": None},
                {
                    "name": "CheatSheetSeries",
                    "fork": False,
                    "archived": False,
                    "description": "OWASP cheat sheets",
                    "language": "Markdown",
                },
                {"name": "forked-tool", "fork": True, "archived": False},
                {
                    "name": "NestJS-demo",
                    "fork": False,
                    "archived": False,
                    "language": "TypeScript",
                    "description": "demo API",
                },
            ]

        plan = resolve_sources(repos_file, list_owner_repos=list_owner)
        opencre_names = {cfg.repo for cfg in plan.opencre}
        self.assertIn("ASVS", opencre_names)
        self.assertIn("CheatSheetSeries", opencre_names)
        self.assertEqual(
            plan.agent, [{"owner": "OWASP", "repo": "NestJS-demo", "dest": "agent"}]
        )
        self.assertGreaterEqual(plan.skipped, 2)

    def test_repositories_only_stays_opencre(self) -> None:
        repos_file = ReposFile.model_validate(
            {
                "repositories": [
                    {
                        "id": "owasp-asvs",
                        "type": "github",
                        "owner": "OWASP",
                        "repo": "ASVS",
                        "paths": {"include": ["**/*.md"]},
                        "chunking": {
                            "strategy": "markdown_heading",
                            "max_tokens": 1200,
                        },
                        "polling": {"mode": "incremental", "interval_minutes": 60},
                    }
                ]
            }
        )
        plan = resolve_sources(
            repos_file, list_owner_repos=lambda owner: self.fail(owner)
        )
        self.assertEqual([cfg.repo for cfg in plan.opencre], ["ASVS"])
        self.assertEqual(plan.agent, [])
