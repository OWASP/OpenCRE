"""Tests for margin / constrained-LLM agent candidate pick."""

from __future__ import annotations

import unittest

from application.utils.owasp_agent.candidate_picker import (
    llm_pick_candidate,
    select_agent_hit,
)
from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, LaneHit
from application.utils.owasp_agent.meta_embeddings import meta_entity_url


def _hit(score: float, key: str, name: str) -> LaneHit:
    return LaneHit(
        CHANNEL_AGENT,
        score,
        content=f"OWASP project: {name}",
        url=meta_entity_url("project", key, "site"),
    )


class TestNarrowCandidates(unittest.TestCase):
    def test_chapter_prompt_restricts_to_chapters(self) -> None:
        from application.utils.owasp_agent.candidate_picker import narrow_candidates

        pool = [
            LaneHit(
                CHANNEL_AGENT,
                0.7,
                url=meta_entity_url("project", "zap", "site"),
                content="ZAP",
            ),
            LaneHit(
                CHANNEL_AGENT,
                0.68,
                url=meta_entity_url("chapter", "berlin", "site"),
                content="Berlin",
            ),
        ]
        narrowed = narrow_candidates("What is the OWASP Berlin chapter?", pool)
        self.assertEqual(len(narrowed), 1)
        self.assertIn("chapter", narrowed[0].url)

    def test_evidence_prompt_restricts_to_evidence(self) -> None:
        from application.utils.owasp_agent.candidate_picker import narrow_candidates
        from application.utils.owasp_agent.meta_embeddings import evidence_url

        pool = [
            LaneHit(
                CHANNEL_AGENT,
                0.7,
                url=meta_entity_url("project", "ai-exchange", "site"),
                content="AI Exchange",
            ),
            LaneHit(
                CHANNEL_AGENT,
                0.66,
                url=evidence_url("lethal-trifecta"),
                content="trifecta",
            ),
        ]
        narrowed = narrow_candidates(
            "lethal trifecta according to OWASP AI Exchange", pool
        )
        self.assertEqual(len(narrowed), 1)
        self.assertTrue(narrowed[0].url.startswith("owasp-agent://evidence/"))


class TestSelectAgentHit(unittest.TestCase):
    def test_clear_margin_picks_top_without_llm(self) -> None:
        calls = {"n": 0}

        def boom(_messages):
            calls["n"] += 1
            raise AssertionError("LLM should not run on clear margin")

        picked = select_agent_hit(
            "What is ASVS?",
            [_hit(0.92, "asvs", "ASVS"), _hit(0.70, "zap", "ZAP")],
            completion_fn=boom,
        )
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertIn("asvs", picked.url)
        self.assertEqual(calls["n"], 0)

    def test_ambiguous_uses_llm_pick(self) -> None:
        def complete(_messages):
            return '{"id": 2}'

        picked = select_agent_hit(
            "security project?",
            [_hit(0.70, "asvs", "ASVS"), _hit(0.68, "zap", "ZAP")],
            completion_fn=complete,
        )
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertIn("zap", picked.url)

    def test_llm_cannot_invent_out_of_range(self) -> None:
        picked = llm_pick_candidate(
            "x",
            [_hit(0.7, "asvs", "ASVS")],
            completion_fn=lambda _m: '{"id": 99}',
        )
        self.assertIsNone(picked)

    def test_lazy_completion_factory_only_when_needed(self) -> None:
        built = {"n": 0}

        def factory():
            built["n"] += 1

            def complete(_m):
                return '{"id": 1}'

            return complete

        select_agent_hit(
            "ASVS",
            [_hit(0.91, "asvs", "ASVS"), _hit(0.50, "zap", "ZAP")],
            get_completion_fn=factory,
        )
        self.assertEqual(built["n"], 0)


class TestRoutePromptTopK(unittest.TestCase):
    def test_route_prompt_fills_agent_candidates(self) -> None:
        from application.utils.owasp_agent.lane_similarity import route_prompt

        def embed(text: str):
            t = text.lower()
            if "asvs" in t:
                return [1.0, 0.0, 0.0]
            if "zap" in t:
                return [0.9, 0.1, 0.0]
            return [0.5, 0.5, 0.0]

        rows = [
            {
                "id": "1",
                "source_channel": CHANNEL_AGENT,
                "embeddings_content": "OWASP project: ASVS",
                "embeddings_url": meta_entity_url("project", "asvs", "site"),
                "doc_type": "OWASP_AGENT_META",
                "embedding_vec": [1.0, 0.0, 0.0],
            },
            {
                "id": "2",
                "source_channel": CHANNEL_AGENT,
                "embeddings_content": "OWASP project: ZAP",
                "embeddings_url": meta_entity_url("project", "zap", "site"),
                "doc_type": "OWASP_AGENT_META",
                "embedding_vec": [0.85, 0.15, 0.0],
            },
            {
                "id": "3",
                "source_channel": "cre_graph",
                "embeddings_content": "CRE password",
                "embeddings_url": "",
                "doc_type": "CRE",
                "embedding_vec": [0.0, 1.0, 0.0],
            },
        ]
        d = route_prompt(
            "What is the OWASP ASVS project please?",
            embed_fn=embed,
            memory_rows=rows,
            top_k=5,
        )
        self.assertGreaterEqual(len(d.agent_candidates), 2)
        self.assertIn("asvs", d.agent_candidates[0].url)


if __name__ == "__main__":
    unittest.main()
