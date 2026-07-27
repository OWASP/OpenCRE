import unittest
from pathlib import Path

from application.utils.harvester.repository_cache import (
    build_repository_cache_path,
)


class RepositoryCacheTests(unittest.TestCase):
    def test_build_repository_cache_path(self):
        path = build_repository_cache_path(
            "OWASP",
            "ASVS",
        )

        self.assertEqual(
            path,
            Path(".harvester_cache/owasp/asvs/main"),
        )

    def test_different_branches_have_different_cache_paths(self):
        main_path = build_repository_cache_path(
            owner="OWASP",
            repository="ASVS",
            branch="main",
        )

        dev_path = build_repository_cache_path(
            owner="OWASP",
            repository="ASVS",
            branch="dev",
        )

        self.assertNotEqual(main_path, dev_path)

    def test_case_sensitive_branches_have_different_cache_paths(self):
        release_path = build_repository_cache_path(
            owner="OWASP",
            repository="ASVS",
            branch="Release",
        )

        release_lower_path = build_repository_cache_path(
            owner="OWASP",
            repository="ASVS",
            branch="release",
        )

        self.assertNotEqual(release_path, release_lower_path)

    def test_path_traversal_owner_rejected(self):
        with self.assertRaises(ValueError):
            build_repository_cache_path(
                owner="../../tmp",
                repository="ASVS",
            )

    def test_absolute_owner_rejected(self):
        with self.assertRaises(ValueError):
            build_repository_cache_path(
                owner="/tmp",
                repository="ASVS",
            )

    def test_invalid_repository_name_rejected(self):
        with self.assertRaises(ValueError):
            build_repository_cache_path(
                owner="OWASP",
                repository="../ASVS",
            )

    def test_branch_path_is_encoded(self):
        path = build_repository_cache_path(
            owner="OWASP",
            repository="ASVS",
            branch="feature/test",
        )

        self.assertNotIn("feature/test", str(path))
        self.assertIn("feature%2Ftest", str(path))


if __name__ == "__main__":
    unittest.main()
