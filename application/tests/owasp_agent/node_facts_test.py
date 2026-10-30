"""Unit tests for node_facts — driven by edge-probe structure product-bads.

Prompts must match
``fixtures/edge_probe_structure_product_bads.jsonl`` exactly (no invented Qs).

Negative answer shape from run_20261016T124604Z/answers/00001.json:
``…is an indexed OWASP project. Leaders: …``
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from application.utils.owasp_agent.node_facts import (
    evidence_docs_from_facts,
    facts_for_cre_id,
    facts_for_name,
    format_facts_message,
    merge_facts_into_metadata,
)

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "edge_probe_structure_product_bads.jsonl"
)

_NEST_BAD = ("indexed OWASP project", "Leaders:")


def _load_fixture() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in _FIXTURE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _family_facts(family: str) -> Dict[str, Any]:
    mapping = {
        "asvs_levels": "ASVS",
        "masvs_levels": "MASVS",
        "samm_levels": "SAMM",
        "aix_layers": "OWASP AI Exchange",
    }
    name = mapping[family]
    facts = facts_for_name(name)
    # Structure questions assert the structure block (AIX also has concept).
    if family == "aix_layers":
        return {"structure": facts["structure"]}
    return facts


class NodeFactsRegistryTest(unittest.TestCase):
    def test_fixture_has_exactly_five_structure_prompts(self) -> None:
        rows = _load_fixture()
        self.assertEqual(len(rows), 5)
        qs = [r["q"] for r in rows]
        self.assertEqual(
            qs,
            [
                "How many levels does OWASP ASVS have?",
                "How many levels / verification levels does OWASP MASVS define?",
                "How many maturity levels does OWASP SAMM use?",
                "How many layers are in the OWASP AI Exchange (AIX) model?",
                "What are the 7 layers of the OWASP AI Exchange?",
            ],
        )

    def test_format_facts_for_each_fixture_prompt(self) -> None:
        for row in _load_fixture():
            with self.subTest(family=row["family"], q=row["q"]):
                facts = _family_facts(row["family"])
                message, citations = format_facts_message(facts)
                self.assertTrue(message, msg=f"empty message for {row['q']}")
                blob = message.lower()
                for needle in row["must_any"]:
                    self.assertIn(
                        needle.lower(),
                        blob,
                        msg=f"{row['q']!r} missing {needle!r} in {message!r}",
                    )
                for bad in row["must_not"]:
                    self.assertNotIn(bad, message)
                for bad in _NEST_BAD:
                    self.assertNotIn(bad, message)
                count = row.get("expect_count")
                if count is not None:
                    self.assertIn(str(count), message)
                self.assertTrue(citations, msg="prefer citations from metadata.facts")
                for cite in citations:
                    self.assertTrue(
                        cite.startswith("http"),
                        msg=f"citation should be URL: {cite}",
                    )

    def test_evidence_docs_cover_structure_families(self) -> None:
        docs = evidence_docs_from_facts()
        self.assertTrue(docs)
        blob = " ".join(d[1] for d in docs).lower()
        for needle in (
            "asvs",
            "masvs",
            "samm",
            "ai exchange",
            "trifecta",
            "verification",
            "maturity",
            "seven",
        ):
            self.assertIn(needle, blob)

    def test_merge_facts_into_metadata(self) -> None:
        facts = facts_for_name("ASVS")
        meta = merge_facts_into_metadata({"other": 1}, facts)
        self.assertEqual(meta["other"], 1)
        self.assertIn("structure", meta["facts"])
        self.assertEqual(meta["facts"]["structure"]["count"], 3)

    def test_cre_facts_migrated_by_id(self) -> None:
        facts = facts_for_cre_id("CRE-844-486")
        message, citations = format_facts_message(facts)
        self.assertIn("CRE-844-486", message)
        self.assertIn("output encoding", message.lower())
        self.assertNotIn("Follow-up:", message)
        self.assertTrue(citations)


def _evidence_embed_for_row(row: Dict[str, Any]) -> str:
    facts = _family_facts(row["family"])
    message, citations = format_facts_message(facts)
    embed = message
    if citations:
        embed += "\n\nCitations: " + ", ".join(citations)
    topics = []
    for block in facts.values():
        if isinstance(block, dict):
            topics.extend(block.get("topics") or [])
    if topics:
        embed += "\n\nTopics: " + ", ".join(str(t) for t in topics)
    return embed


def _nest_project_hit(family: str, score: float = 0.95):
    from application.utils.owasp_agent.lane_similarity import LaneHit
    from application.utils.owasp_agent.meta_embeddings import meta_entity_url

    key_map = {
        "asvs_levels": ("asvs", "ASVS"),
        "masvs_levels": ("masvs", "MASVS"),
        "samm_levels": ("samm", "SAMM"),
        "aix_layers": ("ai-exchange", "OWASP AI Exchange"),
    }
    key, name = key_map[family]
    return LaneHit(
        "owasp_agent_meta",
        score,
        url=meta_entity_url("project", key, "site"),
        content=(
            f"OWASP project: {name}\nkey={key}\n"
            f"{name} is an indexed OWASP project. Leaders: Alice Example."
        ),
    )


class NodeFactsAskRouterTest(unittest.TestCase):
    """ask / router contract for the five frozen structure prompts."""

    def test_router_evidence_wins_over_nest_for_fixture_prompts(self) -> None:
        """Real select_agent_hit: Nest+evidence pool → evidence, never Leaders:."""
        from application.utils.owasp_agent.lane_similarity import LaneHit
        from application.utils.owasp_agent.meta_embeddings import evidence_url
        from application.utils.owasp_agent.router import OwaspAgentRouter

        for row in _load_fixture():
            with self.subTest(family=row["family"], q=row["q"]):
                evidence = LaneHit(
                    "owasp_agent_meta",
                    0.72,
                    url=evidence_url(f"test-{row['family']}"),
                    content=_evidence_embed_for_row(row),
                )
                nest = _nest_project_hit(row["family"], score=0.95)

                class _Dec:
                    action = "agent"
                    reason = "test"
                    scores = {"owasp_agent_meta": 0.95}
                    hits = {"owasp_agent_meta": nest}
                    agent_candidates = [nest, evidence]

                store = MagicMock()
                queries = MagicMock()
                queries.project_lookup.return_value = MagicMock(
                    ok=True,
                    kind="project_lookup",
                    message=(
                        "ASVS is an indexed OWASP project. Leaders: Alice Example."
                    ),
                    citations=[],
                    clarify=None,
                    data={},
                )
                with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
                    with patch(
                        "application.utils.owasp_agent.router._similarity_gate",
                        return_value=_Dec(),
                    ):
                        # Real select_agent_hit / narrow_candidates — do not mock.
                        resp = OwaspAgentRouter(store=store, queries=queries).handle(
                            row["q"]
                        )

                self.assertIsNotNone(resp)
                assert resp is not None
                out_msg = str(resp.get("response") or "")
                for bad in row["must_not"]:
                    self.assertNotIn(bad, out_msg)
                for bad in _NEST_BAD:
                    self.assertNotIn(bad, out_msg)
                queries.project_lookup.assert_not_called()
                lower = out_msg.lower()
                matched = any(n.lower() in lower for n in row["must_any"])
                self.assertTrue(
                    matched,
                    msg=f"{row['q']!r} → {out_msg!r} missing any of {row['must_any']}",
                )
                kind = (resp.get("owasp_agent") or {}).get("kind")
                self.assertEqual(kind, "evidence")

    def test_router_nest_only_defers_structure_fixture_prompts(self) -> None:
        """Nest project alone must not answer structure asks (fail-closed)."""
        from application.utils.owasp_agent.router import OwaspAgentRouter

        for row in _load_fixture():
            with self.subTest(family=row["family"], q=row["q"]):
                nest = _nest_project_hit(row["family"], score=0.95)

                class _Dec:
                    action = "agent"
                    reason = "test"
                    scores = {"owasp_agent_meta": 0.95}
                    hits = {"owasp_agent_meta": nest}
                    agent_candidates = [nest]

                store = MagicMock()
                queries = MagicMock()
                with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
                    with patch(
                        "application.utils.owasp_agent.router._similarity_gate",
                        return_value=_Dec(),
                    ):
                        resp = OwaspAgentRouter(store=store, queries=queries).handle(
                            row["q"]
                        )

                # Defer (None) or any non-Nest answer — never Leaders:/indexed project.
                if resp is not None:
                    out_msg = str(resp.get("response") or "")
                    for bad in row["must_not"]:
                        self.assertNotIn(bad, out_msg)
                    for bad in _NEST_BAD:
                        self.assertNotIn(bad, out_msg)
                queries.project_lookup.assert_not_called()

    @patch("application.utils.owasp_agent.OwaspAgentRouter")
    def test_ask_auto_uses_fixture_prompts(self, router_cls: MagicMock) -> None:
        from application.mcp.ask import CORPUS_AUTO, ask

        for row in _load_fixture():
            with self.subTest(family=row["family"], q=row["q"]):
                facts = _family_facts(row["family"])
                message, citations = format_facts_message(facts)
                router_cls.return_value.handle.return_value = {
                    "response": f"Answer: {message}",
                    "accurate": True,
                    "owasp_agent": {
                        "ok": True,
                        "kind": "evidence",
                        "citations": citations,
                        "data": {"facts": facts},
                    },
                }
                with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
                    with patch(
                        "application.mcp.ask.classify_intent",
                        return_value="cre_normative",
                    ):
                        out = ask(row["q"], corpus=CORPUS_AUTO)

                self.assertTrue(out["ok"])
                for bad in row["must_not"]:
                    self.assertNotIn(bad, out["message"])
                lower = (out["message"] or "").lower()
                self.assertTrue(any(n.lower() in lower for n in row["must_any"]))
                self.assertTrue(out.get("citations"))


class NodeFactsSecurityPathTest(unittest.TestCase):
    def test_security_facts_surfaces_metadata_facts(self) -> None:
        from application.mcp.ask import CORPUS_SECURITY, ask
        from application.tests.mcp_ask_test import _FakeRestClient, _fake_hit

        asvs_facts = facts_for_name("ASVS")
        cre_doc = {
            "id": "111-111",
            "name": "Example",
            "doctype": "CRE",
            "description": "x",
        }
        enriched = {
            "data": {
                "id": "111-111",
                "name": "Example",
                "doctype": "CRE",
                "description": "x",
                "links": [
                    {
                        "document": {
                            "name": "ASVS",
                            "doctype": "Standard",
                            "section": "1.1.1",
                            "hyperlink": "https://example/asvs",
                            "metadata": {"facts": asvs_facts},
                        },
                        "ltype": "Linked To",
                    }
                ],
            }
        }
        client = _FakeRestClient(cres={"111-111": enriched})
        prompt = _load_fixture()[0]["q"]  # exact ASVS fixture prompt
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}, clear=False):
            with patch(
                "application.mcp.ask._retrieve_nearest_standard",
                return_value=_fake_hit(cre_ids=("111-111",)),
            ):
                out = ask(prompt, corpus=CORPUS_SECURITY, rest_client=client)  # type: ignore[arg-type]

        self.assertTrue(out["ok"])
        items = out["items"]
        self.assertTrue(isinstance(items, list))
        fact_items = [i for i in items if isinstance(i, dict) and i.get("facts")]
        self.assertTrue(fact_items, msg="security path must surface metadata.facts")
        # Facts stay on items — must not rewrite the top-level message.
        self.assertNotIn("verification levels", (out.get("message") or "").lower())
        self.assertIn("linked CRE fact item", out["message"])
        message, _ = format_facts_message(asvs_facts)
        for bad in _NEST_BAD:
            self.assertNotIn(bad, message)

    def test_security_facts_skip_linked_standards_for_unrelated_prompt(self) -> None:
        from application.mcp.ask import CORPUS_SECURITY, ask
        from application.tests.mcp_ask_test import _FakeRestClient, _fake_hit

        asvs_facts = facts_for_name("ASVS")
        cre_doc = {
            "id": "111-111",
            "name": "Password Storage",
            "doctype": "CRE",
            "description": "x",
        }
        enriched = {
            "data": {
                "id": "111-111",
                "name": "Password Storage",
                "doctype": "CRE",
                "description": "x",
                "links": [
                    {
                        "document": {
                            "name": "ASVS",
                            "doctype": "Standard",
                            "section": "2.4.1",
                            "hyperlink": "https://example/asvs",
                            "metadata": {"facts": asvs_facts},
                        },
                        "ltype": "Linked To",
                    }
                ],
            }
        }
        client = _FakeRestClient(cres={"111-111": enriched})
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}, clear=False):
            with patch(
                "application.mcp.ask._retrieve_nearest_standard",
                return_value=_fake_hit(cre_ids=("111-111",)),
            ):
                out = ask(
                    "How should I store passwords?",
                    corpus=CORPUS_SECURITY,
                    rest_client=client,  # type: ignore[arg-type]
                )
        self.assertTrue(out["ok"])
        items = out["items"]
        assert isinstance(items, list) and items
        self.assertNotIn("facts", items[0])
        self.assertNotIn("verification levels", (out.get("message") or "").lower())


if __name__ == "__main__":
    unittest.main()
