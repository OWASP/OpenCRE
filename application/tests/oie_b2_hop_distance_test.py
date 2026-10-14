"""Unit tests for B2 CRE hop-distance classification (no DB)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_hop():
    import sys

    path = ROOT / "scripts" / "oie_owasp_eval" / "hop_distance.py"
    name = "oie_hop_distance"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestOieB2HopDistance(unittest.TestCase):
    def setUp(self) -> None:
        self.hop = _load_hop()
        # Graph:
        #   parent --Contains--> child --Related--> cousin
        #   island (known, disconnected)
        edges = [
            self.hop.TypedEdge("parent", "child", "CONTAINS_DOWN"),
            self.hop.TypedEdge("child", "parent", "CONTAINS_UP"),
            self.hop.TypedEdge("child", "cousin", "RELATED"),
            self.hop.TypedEdge("cousin", "child", "RELATED"),
        ]
        self.adj = self.hop.CreAdjacency(
            known_ids=frozenset({"parent", "child", "cousin", "island"}),
            edges=edges,
        )

    def test_exact(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["child", "999-999"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "exact")
        self.assertEqual(row["hop_count"], 0)

    def test_one_hop_related(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["cousin"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "one_hop_related")
        self.assertEqual(row["hop_count"], 1)
        self.assertEqual(row["path_penalty"], 2)

    def test_one_hop_contains_down(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["parent"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "one_hop_contains")
        self.assertEqual(row["hop_count"], 1)
        # parent -> child is CONTAINS_DOWN from parent? Wait: predicted=parent, gold=child
        # path parent -> child is CONTAINS_DOWN, penalty 1
        self.assertEqual(row["path_penalty"], 1)

    def test_one_hop_contains_up(self) -> None:
        row = self.hop.classify_section(
            gold=["parent"], predicted=["child"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "one_hop_contains")
        self.assertEqual(row["hop_count"], 1)
        self.assertEqual(row["path_penalty"], 2)  # CONTAINS_UP

    def test_multi_hop(self) -> None:
        row = self.hop.classify_section(
            gold=["parent"], predicted=["cousin"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "multi_hop")
        self.assertEqual(row["hop_count"], 2)

    def test_hallucination_invented_only(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["zzz-001", "zzz-002"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "hallucination")
        self.assertEqual(sorted(row["invented"]), ["zzz-001", "zzz-002"])

    def test_irrelevant_known_disconnected(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["island"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "irrelevant")

    def test_mixed_known_beats_invented(self) -> None:
        row = self.hop.classify_section(
            gold=["child"], predicted=["zzz-001", "cousin"], adj=self.adj
        )
        self.assertEqual(row["bucket"], "one_hop_related")
        self.assertIn("zzz-001", row["invented"])

    def test_aggregate_percentages(self) -> None:
        details = [
            {"gold": ["child"], "predicted": ["child"], "aligned": True},
            {"gold": ["child"], "predicted": ["cousin"], "aligned": True},
            {"gold": ["child"], "predicted": ["parent"], "aligned": True},
            {"gold": ["parent"], "predicted": ["cousin"], "aligned": True},
            {"gold": ["child"], "predicted": ["zzz-9"], "aligned": True},
            {"gold": ["child"], "predicted": ["island"], "aligned": True},
        ]
        summary = self.hop.score_details(details, self.adj)
        self.assertEqual(summary["scorable"], 6)
        self.assertEqual(summary["counts"]["exact"], 1)
        self.assertEqual(summary["counts"]["one_hop_related"], 1)
        self.assertEqual(summary["counts"]["one_hop_contains"], 1)
        self.assertEqual(summary["counts"]["multi_hop"], 1)
        self.assertEqual(summary["counts"]["hallucination"], 1)
        self.assertEqual(summary["counts"]["irrelevant"], 1)
        self.assertAlmostEqual(summary["rates"]["exact"], 1 / 6, places=4)
        self.assertAlmostEqual(summary["rates"]["distance1_hit"], 3 / 6, places=4)


if __name__ == "__main__":
    unittest.main()
