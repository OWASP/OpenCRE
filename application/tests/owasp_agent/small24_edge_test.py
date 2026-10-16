"""Regression tests for the 24 non-structural edge-probe product misses."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Chapter, Project
from application.utils.owasp_agent.queries import MetaQueries, _match_project
from application.utils.owasp_agent.router import (
    OwaspAgentRouter,
    _sim_meta_ok_for_intent,
    classify_intent,
    extract_slots,
)


class TestSmall24IntentClassify(unittest.TestCase):
    def test_this_year_board_is_board_members(self) -> None:
        self.assertEqual(
            classify_intent("List OWASP board members for this year\nThanks!"),
            "board_members",
        )

    def test_asvs_board_routes_to_project_not_foundation_board(self) -> None:
        for q in (
            "Who are the ASVS board members?",
            "In one sentence: Who are the ASVS board members?\nThanks!",
        ):
            self.assertEqual(classify_intent(q), "project_lookup", q)

    def test_top_ten_leaders_is_project_lookup(self) -> None:
        self.assertEqual(
            classify_intent("Who are the leaders of Owasp Top Ten?"),
            "project_lookup",
        )

    def test_juiceshop_leaders_is_project_lookup(self) -> None:
        self.assertEqual(
            classify_intent(
                "[108] In one sentence: OWASP project JuiceShop (no space) leaders?"
            ),
            "project_lookup",
        )

    def test_ambiguous_chapter_leader_clarifies(self) -> None:
        self.assertEqual(classify_intent("Who is the chapter leader? !!"), "clarify")

    def test_ambiguous_next_meetup_clarifies(self) -> None:
        self.assertEqual(
            classify_intent("When is the next meetup? (source: OWASP.org)"),
            "clarify",
        )

    def test_compare_london_berlin_chapters(self) -> None:
        self.assertEqual(
            classify_intent(
                "Quick question: Compare OWASP London and OWASP Berlin chapters\nThanks!"
            ),
            "chapter_lookup",
        )

    def test_negation_chapter_existence(self) -> None:
        self.assertEqual(
            classify_intent(
                "Which Owasp chapter does NOT exist: London or Atlantis please?"
            ),
            "chapter_lookup",
        )

    def test_juice_and_board_dual_intent(self) -> None:
        self.assertEqual(
            classify_intent(
                "FACT CHECK: WHO LEADS JUICE SHOP AND WHO IS ON THE OWASP BOARD?"
            ),
            "project_and_board",
        )

    def test_cre_bait_project_stays_meta(self) -> None:
        self.assertEqual(
            classify_intent("MAP OWASP JUICE SHOP TO A CRE ID PLEASE"),
            "cre_community_bait",
        )

    def test_cre_bait_chapter_stays_meta(self) -> None:
        self.assertEqual(
            classify_intent(
                "[8] What CRE covers the OWASP Berlin chapter meetup policy?"
            ),
            "cre_community_bait",
        )

    def test_github_slug_is_project_lookup(self) -> None:
        self.assertEqual(
            classify_intent("Fact check: owasp/www-project-juice-shop — what is it?"),
            "project_lookup",
        )

    def test_code_fence_asvs_is_project_lookup(self) -> None:
        self.assertEqual(
            classify_intent(
                "[58] Be precise: ```\nWhat is the OWASP ASVS project?\n```"
            ),
            "project_lookup",
        )


class TestSmall24Slots(unittest.TestCase):
    def test_this_year_resolves_to_current_utc_year(self) -> None:
        slots = extract_slots("List OWASP board members for this year")
        self.assertEqual(slots.year, datetime.now(timezone.utc).year)
        self.assertEqual(slots.years, [datetime.now(timezone.utc).year])

    def test_future_year_2099_kept(self) -> None:
        slots = extract_slots("OWASP board members for year 2099")
        self.assertEqual(slots.year, 2099)

    def test_compare_chapters_extracts_both_places(self) -> None:
        slots = extract_slots("Compare OWASP London and OWASP Berlin chapters")
        places = {p.lower() for p in (slots.places or [])}
        self.assertIn("london", places)
        self.assertIn("berlin", places)

    def test_negation_extracts_both_candidates(self) -> None:
        slots = extract_slots("Which OWASP chapter does NOT exist: London or Atlantis?")
        places = {p.lower() for p in (slots.places or [])}
        self.assertIn("london", places)
        self.assertIn("atlantis", places)

    def test_juiceshop_project_name(self) -> None:
        slots = extract_slots("OWASP project JuiceShop (no space) leaders?")
        self.assertIsNotNone(slots.project_name)
        assert slots.project_name is not None
        self.assertIn("juice", slots.project_name.lower().replace(" ", ""))

    def test_www_project_slug_name(self) -> None:
        slots = extract_slots("owasp/www-project-juice-shop — what is it?")
        self.assertIsNotNone(slots.project_name)
        assert slots.project_name is not None
        self.assertIn("juice", slots.project_name.lower())


class TestSmall24SimGuard(unittest.TestCase):
    def test_events_near_rejects_chapter_meta(self) -> None:
        self.assertFalse(
            _sim_meta_ok_for_intent(
                "events_near", "chapter", "berlin", "meetups near Berlin", None
            )
        )

    def test_events_near_allows_event_meta(self) -> None:
        self.assertTrue(
            _sim_meta_ok_for_intent(
                "events_near", "event", "london-day", "events near London", None
            )
        )

    def test_board_this_year_rejects_wrong_year_card(self) -> None:
        slots = extract_slots("board members for this year")
        year = str(datetime.now(timezone.utc).year)
        self.assertFalse(
            _sim_meta_ok_for_intent(
                "board_members", "board_roster", "2023", "this year", slots
            )
        )
        self.assertTrue(
            _sim_meta_ok_for_intent(
                "board_members", "board_roster", year, "this year", slots
            )
        )

    def test_ambiguous_chapter_rejects_random_chapter_meta(self) -> None:
        self.assertFalse(
            _sim_meta_ok_for_intent(
                "clarify", "chapter", "natori", "Who is the chapter leader?", None
            )
        )


class TestSmall24Queries(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(os.path.join(self.tmp.name, "idx.sqlite"))
        self.store.upsert_project(
            Project(
                key="juice-shop",
                name="OWASP Juice Shop",
                level="flagship",
                description="",
                leaders=["Bjoern Kimminich", "Jannik Hollenbach"],
                source="nest",
            )
        )
        self.store.upsert_project(
            Project(
                key="application-security-verification-standard",
                name="OWASP Application Security Verification Standard (ASVS)",
                level="flagship",
                description="",
                leaders=["Daniel Cuthbert", "Elar Lang", "Josh Grossman"],
                source="nest",
            )
        )
        self.store.upsert_project(
            Project(
                key="top-ten",
                name="OWASP Top Ten Web Application Security Risks",
                level="flagship",
                description="",
                leaders=[
                    "Andrew van der Stock",
                    "Brian Glas",
                    "Neil Smithline",
                    "Torsten Gigler",
                    "Tongke Xue",
                ],
                source="nest",
            )
        )
        self.store.upsert_chapter(
            Chapter(
                key="london",
                name="OWASP London",
                city="London",
                leaders=["Sherif Mansour"],
                active=True,
                url="https://owasp.org/www-chapter-london/",
                source="site",
            )
        )
        self.store.upsert_chapter(
            Chapter(
                key="berlin",
                name="OWASP Berlin",
                city="Berlin",
                leaders=["Andreas Heppner"],
                active=True,
                url="https://owasp.org/www-chapter-berlin/",
                source="site",
            )
        )
        self.queries = MetaQueries(self.store, geocode_fn=lambda p: (52.5, 13.4))
        os.environ["OWASP_AGENT_ENABLED"] = "1"
        os.environ["OWASP_AGENT_SIM_ROUTER"] = "0"
        self.router = OwaspAgentRouter(store=self.store, queries=self.queries)

    def tearDown(self) -> None:
        os.environ.pop("OWASP_AGENT_ENABLED", None)
        os.environ.pop("OWASP_AGENT_SIM_ROUTER", None)
        self.tmp.cleanup()

    def test_match_juiceshop_concat(self) -> None:
        hit = _match_project(self.queries._merged_projects(), "JuiceShop")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["key"], "juice-shop")

    def test_match_www_project_slug(self) -> None:
        hit = _match_project(
            self.queries._merged_projects(), "owasp/www-project-juice-shop"
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["key"], "juice-shop")

    def test_project_lookup_includes_blurb_and_all_leaders(self) -> None:
        result = self.queries.project_lookup("Juice Shop")
        self.assertTrue(result.ok)
        self.assertIn("Bjoern Kimminich", result.message)
        self.assertIn("Jannik Hollenbach", result.message)
        self.assertIn("vulnerable", result.message.lower())

    def test_top_ten_lists_all_leaders(self) -> None:
        result = self.queries.project_lookup("Top Ten")
        self.assertTrue(result.ok)
        self.assertIn("Brian Glas", result.message)
        self.assertIn("Andrew van der Stock", result.message)

    def test_board_missing_year_fail_closed(self) -> None:
        result = self.queries.corpus_entity("board_roster", "2099")
        self.assertFalse(result.ok)
        self.assertIn("2099", result.message)

    def test_compare_london_berlin(self) -> None:
        result = self.queries.chapter_lookup(places=["London", "Berlin"])
        self.assertTrue(result.ok)
        self.assertIn("London", result.message)
        self.assertIn("Berlin", result.message)

    def test_negation_atlantis(self) -> None:
        result = self.queries.chapter_lookup(places=["London", "Atlantis"])
        self.assertTrue(result.ok)
        self.assertIn("Atlantis", result.message)
        self.assertRegex(result.message.lower(), r"no owasp chapter.*atlantis")

    def test_router_asvs_board_names_leaders(self) -> None:
        resp = self.router.handle("Who are the ASVS board members please?")
        self.assertIsNotNone(resp)
        assert resp is not None
        body = resp["response"].lower()
        self.assertIn("asvs", body)
        self.assertIn("daniel cuthbert", body)
        self.assertNotIn("foundation board of directors", body)

    def test_router_ambiguous_chapter_clarifies(self) -> None:
        resp = self.router.handle("Who is the chapter leader?")
        self.assertIsNotNone(resp)
        assert resp is not None
        body = resp["response"].lower()
        self.assertTrue("which" in body or "clarify" in body or "city" in body)
        self.assertNotIn("natori", body)

    def test_router_cre_bait_juice_shop(self) -> None:
        resp = self.router.handle("MAP OWASP JUICE SHOP TO A CRE ID PLEASE")
        self.assertIsNotNone(resp)
        assert resp is not None
        body = resp["response"].lower()
        self.assertIn("juice shop", body)
        self.assertTrue("cre" in body and ("not" in body or "no " in body))

    def test_router_dual_juice_and_board(self) -> None:
        # Seed a board roster overview card.
        self.store.upsert_entity(
            "board_roster",
            "overview",
            "OWASP Board",
            "github",
            {
                "key": "overview",
                "name": "OWASP Board",
                "message": (
                    "The OWASP board is the foundation board of directors. "
                    "Latest indexed year 2026: Sam Stepanyan."
                ),
                "url": "https://github.com/OWASP/www-board/blob/master/_data/board-history.yml",
            },
        )
        resp = self.router.handle("WHO LEADS JUICE SHOP AND WHO IS ON THE OWASP BOARD?")
        self.assertIsNotNone(resp)
        assert resp is not None
        body = resp["response"]
        self.assertIn("Bjoern Kimminich", body)
        self.assertIn("board", body.lower())

    def test_router_events_near_berlin_mentions_meetups_or_none(self) -> None:
        resp = self.router.handle("Find OWASP meetups near Berlin")
        self.assertIsNotNone(resp)
        assert resp is not None
        body = resp["response"].lower()
        self.assertIn("berlin", body)
        self.assertTrue(
            "meetup" in body
            or "event" in body
            or "upcoming" in body
            or "not indexed" in body
            or "no matching" in body
        )


if __name__ == "__main__":
    unittest.main()
