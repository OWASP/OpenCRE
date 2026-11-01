import unittest

from application.utils.owasp_agent.queries import (
    _metro_chapter_alias,
    _project_fallback_blurb,
)
from scripts.seed_node_facts import _build_parser


class ProjectFallbackBlurbTest(unittest.TestCase):
    def test_known_project_keeps_its_blurb(self) -> None:
        self.assertIn(
            "Juice Shop", _project_fallback_blurb({"key": "juice-shop", "name": ""})
        )
        self.assertIn(
            "Juice Shop", _project_fallback_blurb({"key": "", "name": "Juice Shop"})
        )

    def test_empty_key_and_name_get_no_blurb(self) -> None:
        self.assertEqual(_project_fallback_blurb({"key": "", "name": ""}), "")
        self.assertEqual(_project_fallback_blurb({}), "")

    def test_short_fragments_do_not_substring_match(self) -> None:
        self.assertEqual(_project_fallback_blurb({"key": "ten", "name": "ten"}), "")


class MetroAliasTest(unittest.TestCase):
    def test_cambridge_is_not_aliased_to_boston(self) -> None:
        self.assertIsNone(_metro_chapter_alias("Cambridge"))
        self.assertIsNone(_metro_chapter_alias("Cambridge, UK"))

    def test_other_metro_aliases_still_resolve(self) -> None:
        self.assertEqual(_metro_chapter_alias("Brooklyn"), "new york")


class SeedNodeFactsArgsTest(unittest.TestCase):
    def test_node_metadata_seeding_is_opt_in(self) -> None:
        self.assertFalse(_build_parser().parse_args([]).seed_nodes)
        self.assertTrue(_build_parser().parse_args(["--seed-nodes"]).seed_nodes)


if __name__ == "__main__":
    unittest.main()
