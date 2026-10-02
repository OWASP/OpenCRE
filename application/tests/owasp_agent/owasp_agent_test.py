"""OWASP agent demo scenario tests (offline fixtures, no live network)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from application.utils.owasp_agent.concepts import (
    auto_concepts_from_index,
    maybe_create_concept,
    merge_near_duplicate_concepts,
)
from application.utils.owasp_agent.github_crawler import (
    GitHubCrawler,
    parse_board_history_yaml,
)
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Chapter, Event, Project
from application.utils.owasp_agent.queries import MetaQueries
from application.utils.owasp_agent.router import (
    OwaspAgentRouter,
    classify_intent,
    extract_slots,
    format_chat_response,
)
from application.utils.owasp_agent.sync import sync_all

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_store(db_path: str) -> IndexStore:
    store = IndexStore(db_path)
    text = (FIXTURES / "board-history.yml").read_text()
    members, candidates = parse_board_history_yaml(text)
    for m in members:
        store.upsert_board_member(m)
    for c in candidates:
        store.upsert_board_candidate(c)

    crawler = GitHubCrawler()
    ch = crawler.parse_chapter_markdown(
        "OWASP/www-chapter-los-angeles", (FIXTURES / "chapter-la.md.txt").read_text()
    )
    store.upsert_chapter(ch)
    # Nest copy of same chapter (no conflict)
    nest_ch = Chapter(
        key=ch.key,
        name=ch.name,
        country=ch.country,
        region=ch.region,
        city=ch.city,
        latitude=ch.latitude,
        longitude=ch.longitude,
        url="https://nest.owasp.org/chapters/los-angeles",
        tags=ch.tags,
        source="nest",
    )
    store.upsert_chapter(nest_ch)

    proj = crawler.parse_project_markdown(
        "OWASP/www-project-machine-learning-security-top-10",
        (FIXTURES / "project-ml.md.txt").read_text(),
    )
    store.upsert_project(proj)
    store.upsert_project(
        Project(
            key="zap",
            name="OWASP Zed Attack Proxy",
            level="flagship",
            description="Web appsec proxy",
            url="https://owasp.org/www-project-zap/",
            tags=["appsec", "web"],
            source="nest",
        )
    )
    store.upsert_project(
        Project(
            key="asvs",
            name="Application Security Verification Standard",
            level="flagship",
            description="AppSec verification",
            tags=["appsec", "asvs"],
            source="github",
        )
    )

    # Upcoming AI event near LA
    store.upsert_event(
        Event(
            key="la-ai-meetup",
            name="OWASP LA AI Security Meetup",
            start_date="2099-06-15T18:00:00+00:00",
            chapter_key="los-angeles",
            city="Los Angeles",
            latitude=34.05,
            longitude=-118.25,
            url="https://example.com/la-ai",
            description="Talks on AI security",
            topics=["ai security"],
            talks=["Intro to LLM security", "Prompt injection 101"],
            source="nest",
        )
    )
    # Past event
    store.upsert_event(
        Event(
            key="la-past",
            name="OWASP LA Past Meetup",
            start_date="2020-01-01T18:00:00+00:00",
            chapter_key="los-angeles",
            city="Los Angeles",
            latitude=34.05,
            longitude=-118.25,
            url="https://example.com/la-past",
            topics=["appsec"],
            talks=["Old talk"],
            source="nest",
        )
    )
    # Far away event
    store.upsert_event(
        Event(
            key="london-ai",
            name="OWASP London AI Night",
            start_date="2099-07-01T18:00:00+00:00",
            city="London",
            latitude=51.5,
            longitude=-0.12,
            url="https://example.com/london",
            topics=["ai"],
            source="nest",
        )
    )
    return store


class TestOwaspAgentScenarios(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "agent.sqlite")
        self.store = _seed_store(self.db_path)
        self.queries = MetaQueries(
            self.store, geocode_fn=lambda place: (34.1478, -118.1445)  # Pasadena
        )
        self.router = OwaspAgentRouter(store=self.store, queries=self.queries)
        os.environ["OWASP_AGENT_ENABLED"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("OWASP_AGENT_ENABLED", None)
        self.tmp.cleanup()

    def test_nearest_ai_meetup_pasadena(self) -> None:
        result = self.queries.events_near(
            place="Pasadena, California",
            topic="ai_security",
            upcoming_only=True,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(result.ok)
        self.assertIn("Pasadena", result.message)
        self.assertIn("OWASP LA", result.message)
        self.assertIn("LLM security", result.message)
        self.assertNotIn("Past Meetup", result.message)
        self.assertNotIn("London", result.message)

    def test_nearest_without_city_asks(self) -> None:
        result = self.queries.events_near(place=None)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.clarify)
        self.assertIn("city", (result.clarify or "").lower())

    def test_count_chapters(self) -> None:
        result = self.queries.count_chapters()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 1)

    def test_count_ai_projects(self) -> None:
        result = self.queries.count_projects(topic="ai_security")
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.data["count"], 1)
        self.assertIn("ai_security", result.message)

    def test_count_appsec_projects(self) -> None:
        result = self.queries.count_projects(topic="appsec")
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.data["count"], 2)

    def test_ambiguous_topic_fail_closed(self) -> None:
        result = self.queries.count_projects(topic="quantum-frobinators")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.clarify)

    def test_board_person_alice(self) -> None:
        result = self.queries.board_person("Alice Example")
        self.assertTrue(result.ok)
        self.assertIn(2020, result.data["member_years"])
        self.assertIn(2021, result.data["member_years"])

    def test_board_members_year(self) -> None:
        result = self.queries.board_members(2020)
        self.assertTrue(result.ok)
        self.assertIn("Alice Example", result.data["members"])

    def test_candidate_stats(self) -> None:
        result = self.queries.board_candidate_stats(
            ["Carol Candidate", "Dave Candidate", "Eve Candidate"]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["Dave Candidate"]["candidate_count"], 3)
        self.assertEqual(result.data["Eve Candidate"]["candidate_count"], 1)

    def test_past_events_allowed(self) -> None:
        result = self.queries.events_near(
            place="Pasadena",
            upcoming_only=False,
            include_past=True,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(result.ok)
        names = [e["name"] for e in result.data["events"]]
        self.assertTrue(any("Past" in n for n in names))

    def test_empty_index_count_fail_closed(self) -> None:
        empty = IndexStore(os.path.join(self.tmp.name, "empty.sqlite"))
        q = MetaQueries(empty, geocode_fn=lambda p: (0.0, 0.0))
        result = q.count_chapters()
        self.assertFalse(result.ok)
        self.assertIn("indexed yet", result.message.lower())

    def test_conflicted_chapter_count_excluded(self) -> None:
        store = IndexStore(os.path.join(self.tmp.name, "conflict-count.sqlite"))
        store.upsert_chapter(
            Chapter(
                key="x",
                name="X Nest",
                country="US",
                latitude=10.0,
                longitude=10.0,
                source="nest",
            )
        )
        store.upsert_chapter(
            Chapter(
                key="x",
                name="X GitHub",
                country="UK",
                latitude=50.0,
                longitude=50.0,
                source="github",
            )
        )
        q = MetaQueries(store, geocode_fn=lambda p: (0.0, 0.0))
        result = q.count_chapters()
        self.assertFalse(result.ok)
        self.assertIn("conflict", result.message.lower())

    def test_topic_ai_not_match_details_substring(self) -> None:
        store = IndexStore(os.path.join(self.tmp.name, "topic.sqlite"))
        store.upsert_project(
            Project(
                key="details",
                name="Project Details Guide",
                description="email details here",
                tags=["docs"],
                source="nest",
            )
        )
        store.upsert_project(
            Project(
                key="ml",
                name="ML Sec",
                description="machine learning security",
                tags=["AI"],
                source="nest",
            )
        )
        q = MetaQueries(store, geocode_fn=lambda p: (0.0, 0.0))
        result = q.count_projects(topic="ai_security")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 1)

    def test_router_defers_normative_to_cre(self) -> None:
        self.assertIsNone(self.router.handle("How should I store passwords securely?"))
        self.assertEqual(
            classify_intent("How should I store passwords securely?"),
            "cre_normative",
        )

    def test_router_meetup_clarifies_without_city(self) -> None:
        resp = self.router.handle(
            "I am a developer making an AI system. Give me the nearest OWASP meetup about AI security."
        )
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertIn("city", resp["response"].lower())
        self.assertEqual(resp["model_name"], "owasp-agent-router")

    def test_router_meetup_with_city(self) -> None:
        resp = self.router.handle(
            "Nearest OWASP meetup on AI security; I am in Pasadena, California."
        )
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertIn("Pasadena", resp["response"])
        self.assertIn("OWASP LA", resp["response"])

    def test_router_disabled_returns_none(self) -> None:
        os.environ["OWASP_AGENT_ENABLED"] = "0"
        self.assertIsNone(self.router.handle("How many OWASP chapters are there?"))

    def test_router_count_chapters(self) -> None:
        resp = self.router.handle("How many OWASP chapters are there?")
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertIn("1", resp["response"])

    def test_extract_slots_place_and_year(self) -> None:
        slots = extract_slots("Board members in 2021 near Los Angeles")
        self.assertEqual(slots.year, 2021)
        self.assertEqual(slots.place, "Los Angeles")

    def test_strict_concepts_and_merge(self) -> None:
        actions = auto_concepts_from_index(self.store)
        created = [a for a in actions if a.action == "created"]
        self.assertTrue(created)
        # Near-duplicate create should reuse
        again = maybe_create_concept(
            self.store,
            name="OWASP Los Angeles Chapter",
            category="Community",
            evidence_urls=["https://owasp.org/www-chapter-los-angeles/"],
            entity_keys=["chapter:los-angeles-dup"],
        )
        self.assertEqual(again.action, "reused")
        # Force a high-similarity duplicate concept then merge
        maybe_create_concept(
            self.store,
            name="OWASP Los Angeles",
            category="Community",
            evidence_urls=["https://example.com/dup"],
            entity_keys=["chapter:forced-dup"],
        )
        # Create an almost identical second concept with different key by bypassing maybe_create
        from application.utils.owasp_agent.models import Concept

        self.store.upsert_concept(
            Concept(
                key="community:owasp-los-angeles-alt",
                name="OWASP Los Angeles",
                category="Community",
                evidence_urls=["https://example.com/alt"],
                entity_keys=["chapter:alt"],
            )
        )
        merges = merge_near_duplicate_concepts(self.store, threshold=0.85)
        self.assertTrue(len(merges) >= 1)

    def test_skip_concept_without_evidence(self) -> None:
        action = maybe_create_concept(self.store, name="Orphan Idea", category="Other")
        self.assertEqual(action.action, "skipped")

    def test_format_chat_response(self) -> None:
        from application.utils.owasp_agent.models import QueryResult

        payload = format_chat_response(
            QueryResult(
                ok=True,
                kind="count_chapters",
                message="There are 1 chapters.",
                citations=["http://x"],
            )
        )
        self.assertTrue(payload["response"].startswith("Answer:"))
        self.assertEqual(payload["table"][0]["link"], "http://x")

    def test_sync_github_board_only(self) -> None:
        class FakeGH:
            def fetch_board_history(self):
                text = (FIXTURES / "board-history.yml").read_text()
                return parse_board_history_yaml(text)

        store = IndexStore(os.path.join(self.tmp.name, "sync.sqlite"))
        report = sync_all(
            store=store,
            skip_nest=True,
            github=FakeGH(),  # type: ignore[arg-type]
            github_chapter_repos=[],
            github_project_repos=[],
        )
        self.assertTrue(report.github_ok)
        self.assertGreaterEqual(report.board_members, 1)

    def test_github_frontmatter_parse(self) -> None:
        crawler = GitHubCrawler()
        ch = crawler.parse_chapter_markdown(
            "OWASP/www-chapter-los-angeles",
            (FIXTURES / "chapter-la.md.txt").read_text(),
        )
        self.assertEqual(ch.city, "Los Angeles")
        self.assertAlmostEqual(ch.latitude or 0, 34.0522, places=3)


class TestNestClientParsing(unittest.TestCase):
    def test_parse_project_from_dict(self) -> None:
        from application.utils.owasp_agent.nest_client import NestClient

        p = NestClient._parse_project(
            {
                "key": "zap",
                "name": "ZAP",
                "level": "flagship",
                "tags": ["appsec"],
                "url": "https://nest.owasp.org/projects/zap",
            }
        )
        self.assertEqual(p.key, "zap")
        self.assertEqual(p.source, "nest")


if __name__ == "__main__":
    unittest.main()
