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


if __name__ == "__main__":
    unittest.main()
