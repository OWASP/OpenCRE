import importlib.util
import tempfile
import unittest
from pathlib import Path

from application.utils.harvester.config_loader import load_repo_config
from application.utils.harvester.repos_validator import validate_repositories

ROOT = Path(__file__).resolve().parents[2]
CURATED = ROOT / "application" / "utils" / "harvester" / "repos.curated.yaml"


def _load():
    spec = importlib.util.spec_from_file_location(
        "oie_generate_repos_yaml", ROOT / "scripts" / "oie_generate_repos_yaml.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORG = [
    {"name": "www-chapter-london", "default_branch": "master"},
    {"name": "www-event-global-appsec", "default_branch": "main"},
    {"name": "www-project-top-ten", "default_branch": "master"},
    {"name": "juice-shop", "default_branch": "master"},
    {"name": "ASVS", "default_branch": "master"},
    {"name": "some-fork", "default_branch": "main", "fork": True},
    {"name": "true", "default_branch": "main"},
]


class GenerateReposYamlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_classify_repo(self) -> None:
        self.assertEqual(self.mod.classify_repo("www-chapter-x"), "chapter")
        self.assertEqual(self.mod.classify_repo("WWW-Event-x"), "event")
        self.assertEqual(self.mod.classify_repo("www-project-x"), "project")
        self.assertEqual(self.mod.classify_repo("www-committee-x"), "other")
        self.assertEqual(self.mod.classify_repo("ZAP"), "other")

    def _render_and_load(self, **kwargs):
        text = self.mod.render_repos_yaml(ORG, CURATED.read_text(), **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repos.yaml"
            path.write_text(text)
            cfg = load_repo_config(path)
        validate_repositories(cfg)
        return text, cfg

    def test_output_validates_and_routes_by_kind(self) -> None:
        _, cfg = self._render_and_load()
        by_repo = {r.repo: r for r in cfg.repositories}
        self.assertEqual(by_repo["www-chapter-london"].kind, "chapter")
        self.assertEqual(by_repo["www-event-global-appsec"].kind, "event")
        self.assertEqual(by_repo["www-project-top-ten"].kind, "project")
        self.assertEqual(by_repo["juice-shop"].kind, "other")
        self.assertEqual(by_repo["www-project-top-ten"].branch, "master")
        self.assertEqual(by_repo["www-project-top-ten"].polling.interval_minutes, 1440)

    def test_curated_entries_win_and_are_not_duplicated(self) -> None:
        _, cfg = self._render_and_load()
        asvs = [r for r in cfg.repositories if r.repo == "ASVS"]
        self.assertEqual(len(asvs), 1)
        self.assertEqual(asvs[0].id, "owasp-asvs")
        self.assertEqual(asvs[0].chunking.strategy, "docling")
        self.assertEqual(asvs[0].kind, "standard")

    def test_forks_skipped_unless_requested(self) -> None:
        _, cfg = self._render_and_load()
        self.assertNotIn("some-fork", {r.repo for r in cfg.repositories})
        _, cfg = self._render_and_load(include_forks=True)
        self.assertIn("some-fork", {r.repo for r in cfg.repositories})

    def test_yaml_hostile_repo_name_stays_a_string(self) -> None:
        _, cfg = self._render_and_load()
        self.assertIn("true", {r.repo for r in cfg.repositories})


class ShippedReposYamlTest(unittest.TestCase):
    def test_shipped_file_is_in_sync_with_curated_entries(self) -> None:
        shipped = load_repo_config(
            ROOT / "application" / "utils" / "harvester" / "repos.yaml"
        )
        curated = load_repo_config(CURATED)
        shipped_ids = {r.id for r in shipped.repositories}
        for repo in curated.repositories:
            self.assertIn(repo.id, shipped_ids)
        validate_repositories(shipped)


if __name__ == "__main__":
    unittest.main()
