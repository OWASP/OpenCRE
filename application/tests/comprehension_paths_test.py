import unittest

from application.utils.comprehension import paths
from application.utils.comprehension.sources import is_noise_path


class TestPaths(unittest.TestCase):
    def test_asset_and_vendored_paths_are_not_indexed(self):
        for p in (
            "www-project-top-ten/assets/images/README.md",
            "a/img/README.md",
            "a/static/readme.md",
            "spotlight/vendor/bundle/ruby/3.3.0/gems/ethon/CHANGELOG.md",
            "a/node_modules/x/readme.md",
        ):
            self.assertTrue(paths.is_asset_path(p), p)
            self.assertTrue(is_noise_path(p), p)

    def test_real_content_stays(self):
        for p in (
            "docs/threat-modeling.md",
            "assets/guide/overview.md",
            "www-board/meetings-historical/2025/202503.md",
            "README.md",
        ):
            self.assertFalse(paths.is_asset_path(p), p)

    def test_low_value_paths_rank_a_little_lower_and_cite_last(self):
        self.assertEqual(paths.priority("docs/a.md"), 1.0)
        self.assertLess(paths.priority("old-versions/V1/a.md"), 1.0)
        urls = ["x/old-versions/a.md", "x/b.md", "x/c.md", "x/d.md"]
        self.assertEqual(paths.order_and_cap(urls, 3), ["x/b.md", "x/c.md", "x/d.md"])
        self.assertEqual(
            paths.order_and_cap(urls[:2], 5), ["x/b.md", "x/old-versions/a.md"]
        )


if __name__ == "__main__":
    unittest.main()
