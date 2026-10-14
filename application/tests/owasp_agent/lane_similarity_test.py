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

    def test_evidence_documents_include_trifecta_prose(self) -> None:
        docs = evidence_documents()
        self.assertTrue(docs)
        blob = " ".join(d[1] for d in docs).lower()
        self.assertIn("trifecta", blob)
        self.assertIn("exfiltration", blob)


if __name__ == "__main__":
    unittest.main()
