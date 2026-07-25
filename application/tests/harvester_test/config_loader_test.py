from pathlib import Path
import unittest

from application.utils.harvester.config_loader import (
    ConfigLoaderError,
    ConfigFileNotFoundError,
    load_repo_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ConfigLoaderTests(unittest.TestCase):
    def test_load_valid_config(self):
        config_path = FIXTURES_DIR / "valid_repos.yaml"

        config = load_repo_config(config_path)

        self.assertEqual(len(config.repositories), 1)

        repo = config.repositories[0]

        self.assertEqual(repo.id, "owasp-asvs")
        self.assertEqual(repo.owner, "OWASP")
        self.assertEqual(repo.repo, "ASVS")

    def test_missing_repository_id(self):
        config_path = FIXTURES_DIR / "invalid_missing_id.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_invalid_chunk_size(self):
        config_path = FIXTURES_DIR / "invalid_chunk_size.yaml"

        with self.assertRaisesRegex(ConfigLoaderError, "max_tokens"):
            load_repo_config(config_path)

    def test_invalid_yaml_syntax(self):
        config_path = FIXTURES_DIR / "invalid_yaml.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_missing_config_file(self):
        with self.assertRaises(ConfigFileNotFoundError):
            load_repo_config("does_not_exist.yaml")

    def test_invalid_polling_interval(self):
        config_path = FIXTURES_DIR / "invalid_polling_interval.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_empty_include_paths(self):
        config_path = FIXTURES_DIR / "empty_include_paths.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_whitespace_only_repository_id(self):
        config_path = FIXTURES_DIR / "whitespace_id.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_whitespace_only_owner(self):
        config_path = FIXTURES_DIR / "whitespace_owner.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_whitespace_only_repo(self):
        config_path = FIXTURES_DIR / "whitespace_repo.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_whitespace_only_branch(self):
        config_path = FIXTURES_DIR / "whitespace_branch.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_overlap_tokens_must_be_less_than_max_tokens(self):
        config_path = FIXTURES_DIR / "invalid_overlap_tokens.yaml"

        with self.assertRaisesRegex(ConfigLoaderError, "overlap_tokens"):
            load_repo_config(config_path)

    def test_load_packaged_repos_yaml(self):
        config_path = (
            Path(__file__).resolve().parents[2] / "utils" / "harvester" / "repos.yaml"
        )

        config = load_repo_config(config_path)

        self.assertEqual(len(config.repositories), 2)
        self.assertEqual(config.repositories[0].id, "owasp-asvs")
        self.assertEqual(config.repositories[1].id, "owasp-cheatsheets")

    def test_empty_owner(self):
        config_path = FIXTURES_DIR / "empty_owner.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_invalid_chunking_strategy(self):
        config_path = FIXTURES_DIR / "invalid_chunking_strategy.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)

    def test_invalid_polling_mode(self):
        config_path = FIXTURES_DIR / "invalid_polling_mode.yaml"

        with self.assertRaises(ConfigLoaderError):
            load_repo_config(config_path)


if __name__ == "__main__":
    unittest.main()
