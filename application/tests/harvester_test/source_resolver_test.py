from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from unittest import mock
import urllib.error

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


class GithubSourceProbeTests(unittest.TestCase):
    def test_org_ok_and_repo_ok(self) -> None:
        from application.utils.harvester.github_sources import probe_github_source

        def urlopen(req, timeout=None):
            self.assertIn("api.github.com", req.full_url)
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = b"{}"
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        with mock.patch(
            "application.utils.harvester.github_sources.urllib.request.urlopen",
            side_effect=urlopen,
        ):
            probe_github_source(parse_github_source("github.com/OWASP/"))
            probe_github_source(parse_github_source("github.com/OWASP/ASVS"))

    def test_org_not_found_and_timeout(self) -> None:
        from application.utils.harvester.github_sources import probe_github_source

        def not_found(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", hdrs=None, fp=None
            )

        with mock.patch(
            "application.utils.harvester.github_sources.urllib.request.urlopen",
            side_effect=not_found,
        ):
            with self.assertRaises(ValueError) as ctx:
                probe_github_source(parse_github_source("github.com/NoSuchOrgCcdd/"))
            self.assertIn("not accessible", str(ctx.exception))
            self.assertIn("github.com/NoSuchOrgCcdd/", str(ctx.exception))

        def timed_out(req, timeout=None):
            raise urllib.error.URLError(TimeoutError("timed out"))

        with mock.patch(
            "application.utils.harvester.github_sources.urllib.request.urlopen",
            side_effect=timed_out,
        ):
            with self.assertRaises(ValueError) as ctx:
                probe_github_source(parse_github_source("github.com/OWASP/"))
            self.assertIn("timed out", str(ctx.exception))
            self.assertIn("github.com/OWASP/", str(ctx.exception))


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

    def test_source_cron_copied_onto_discovered_repos(self) -> None:
        repos_file = ReposFile.model_validate(
            {
                "sources": [
                    {"url": "github.com/OWASP/", "cron": "0 2 * * *"},
                ]
            }
        )

        def list_owner(owner: str):
            return [
                {"name": "ASVS", "fork": False, "archived": False, "language": None},
                {
                    "name": "NestJS-demo",
                    "fork": False,
                    "archived": False,
                    "language": "TypeScript",
                    "description": "demo API",
                },
            ]

        plan = resolve_sources(repos_file, list_owner_repos=list_owner)
        asvs = next(cfg for cfg in plan.opencre if cfg.repo == "ASVS")
        self.assertEqual(asvs.cron, "0 2 * * *")
        self.assertEqual(plan.agent[0]["cron"], "0 2 * * *")

    def test_disabled_source_is_skipped(self) -> None:
        repos_file = ReposFile.model_validate(
            {"sources": [{"url": "github.com/OWASP/", "enabled": False}]}
        )
        plan = resolve_sources(
            repos_file, list_owner_repos=lambda owner: self.fail(owner)
        )
        self.assertEqual(plan.opencre, [])
        self.assertEqual(plan.skipped, 1)

    def test_invalid_cron_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            ReposFile.model_validate(
                {"sources": [{"url": "github.com/OWASP/", "cron": "hourly"}]}
            )
