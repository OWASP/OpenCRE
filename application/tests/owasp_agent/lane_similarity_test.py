"""Unit tests for multi-lane embedding routing (no brand classifiers)."""

from __future__ import annotations

import unittest

from application.utils.owasp_agent.lane_similarity import (
    CHANNEL_AGENT,
    CHANNEL_CORPUS,
    CHANNEL_CRE,
    LaneHit,
    decide_lanes,
    is_evidence_hit,
    route_prompt,
)
from application.utils.owasp_agent.meta_embeddings import (
    evidence_documents,
    evidence_url,
    meta_entity_url,
    text_for_meta_entity,
)


class TestDecideLanes(unittest.TestCase):
    def test_all_weak_clarifies(self) -> None:
        hits = {
            CHANNEL_CRE: LaneHit(CHANNEL_CRE, 0.2),
            CHANNEL_CORPUS: LaneHit(CHANNEL_CORPUS, 0.1),
            CHANNEL_AGENT: LaneHit(CHANNEL_AGENT, 0.15),
        }
        d = decide_lanes(hits)
        self.assertEqual(d.action, "clarify")

    def test_agent_dominates(self) -> None:
        hits = {
            CHANNEL_CRE: LaneHit(CHANNEL_CRE, 0.4),
            CHANNEL_CORPUS: LaneHit(CHANNEL_CORPUS, 0.3),
            CHANNEL_AGENT: LaneHit(CHANNEL_AGENT, 0.9, content="Rob leads AI"),
        }
        d = decide_lanes(hits)
        self.assertEqual(d.action, "agent")

    def test_cre_dominates(self) -> None:
        hits = {
            CHANNEL_CRE: LaneHit(CHANNEL_CRE, 0.91, content="ASVS password"),
            CHANNEL_CORPUS: LaneHit(CHANNEL_CORPUS, 0.5),
            CHANNEL_AGENT: LaneHit(CHANNEL_AGENT, 0.4),
        }
        d = decide_lanes(hits)
        self.assertEqual(d.action, "cre")

    def test_both_when_close(self) -> None:
        hits = {
            CHANNEL_CRE: LaneHit(CHANNEL_CRE, 0.72),
            CHANNEL_CORPUS: LaneHit(CHANNEL_CORPUS, 0.5),
            CHANNEL_AGENT: LaneHit(CHANNEL_AGENT, 0.70),
        }
        d = decide_lanes(hits)
        self.assertEqual(d.action, "both")


class TestRoutePromptMemory(unittest.TestCase):
    def test_memory_rows_pick_agent_for_leader_text(self) -> None:
        # Tiny bag-of-orthogonal vectors so cosine is deterministic.
        def embed(text: str):
            t = text.lower()
            if "rob" in t or "leader" in t:
                return [1.0, 0.0, 0.0]
            if "asvs" in t or "password" in t:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        rows = [
            {
                "id": "1",
                "source_channel": CHANNEL_AGENT,
                "embeddings_content": "OWASP project_leader: Rob van der Veer",
                "embeddings_url": meta_entity_url("project_leader", "rob", "site"),
                "doc_type": "OWASP_AGENT_META",
                "embedding_vec": [1.0, 0.0, 0.0],
            },
            {
                "id": "2",
                "source_channel": CHANNEL_CRE,
                "embeddings_content": "ASVS password storage",
                "embeddings_url": "",
                "doc_type": "CRE",
                "embedding_vec": [0.0, 1.0, 0.0],
            },
        ]
        d = route_prompt(
            "Who is Rob van der Veer?",
            embed_fn=embed,
            memory_rows=rows,
        )
        self.assertEqual(d.action, "agent")
        self.assertIn(
            "Rob", (d.hits[CHANNEL_AGENT].content if d.hits[CHANNEL_AGENT] else "")
        )

    def test_evidence_hit_detected(self) -> None:
        hit = LaneHit(
            CHANNEL_AGENT,
            0.9,
            url=evidence_url("lethal-trifecta"),
            content="trifecta text",
        )
        self.assertTrue(is_evidence_hit(hit))
        self.assertFalse(
            is_evidence_hit(LaneHit(CHANNEL_AGENT, 0.9, url="owasp-agent://meta/x"))
        )


class TestMetaEmbeddingText(unittest.TestCase):
    def test_text_for_meta_includes_leaders(self) -> None:
        text = text_for_meta_entity(
            {
                "kind": "project",
                "key": "ai-exchange",
                "name": "OWASP AI Exchange",
                "leaders": ["Rob van der Veer"],
                "description": "AI security guidance",
            }
        )
        self.assertIn("Rob van der Veer", text)
        self.assertIn("AI Exchange", text)
        # Nest project embeds must not carry structure/facts appendix.
        self.assertNotIn("seven protection layers", text.lower())
        self.assertNotIn("verification levels", text.lower())
        self.assertNotIn("Topics:", text)

    def test_evidence_documents_include_trifecta_prose(self) -> None:
        docs = evidence_documents()
        self.assertTrue(docs)
        blob = " ".join(d[1] for d in docs).lower()
        self.assertIn("trifecta", blob)
        self.assertIn("exfiltration", blob)
        self.assertIn("ai exchange", blob)

    def test_chapter_embed_text_has_paraphrase_topics(self) -> None:
        text = text_for_meta_entity(
            {
                "kind": "chapter",
                "key": "berlin",
                "name": "OWASP Berlin",
                "city": "Berlin",
                "country": "Germany",
                "leaders": ["Ada"],
            }
        )
        low = text.lower()
        self.assertIn("berlin chapter", low)
        self.assertIn("chapter in berlin", low)

    def test_materialize_board_ontology(self) -> None:
        import tempfile
        from pathlib import Path

        from application.utils.owasp_agent.index_store import IndexStore
        from application.utils.owasp_agent.meta_embeddings import (
            materialize_board_ontology,
        )
        from application.utils.owasp_agent.models import BoardMember

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "t.sqlite")
            store = IndexStore(db)
            store.upsert_board_member(
                BoardMember(
                    name="Alice Example",
                    year=2020,
                    role="member",
                    source="github",
                )
            )
            n = materialize_board_ontology(store)
            self.assertGreaterEqual(n, 2)
            rosters = store.list_entities("board_roster")
            keys = {str(r.get("key")) for r in rosters}
            self.assertIn("2020", keys)
            self.assertIn("overview", keys)
            overview = next(r for r in rosters if r.get("key") == "overview")
            self.assertIn("Alice Example", overview.get("message") or "")


if __name__ == "__main__":
    unittest.main()
