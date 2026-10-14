"""Tests for optional hub→leaf Contains cage."""

from __future__ import annotations

import unittest

from application.utils.librarian.hub_leaf_cage import HubLeafCageRetriever
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.umbrella_promote import ParentIndex


class _RecordingRetriever:
    def __init__(self, hits_by_call: list[list[tuple[str, float]]]) -> None:
        self._hits = list(hits_by_call)
        self.allowlists: list[object] = []
        self.texts: list[str] = []

    def retrieve(self, text: str, *, allowlist=None) -> RetrievalAudit:
        self.texts.append(text)
        self.allowlists.append(allowlist)
        hits = self._hits.pop(0) if self._hits else []
        if allowlist is not None:
            hits = [(cid, s) for cid, s in hits if cid in allowlist]
        return RetrievalAudit(
            retriever="rec",
            candidates=[
                CreCandidate(cre_id=cid, score_vector=score) for cid, score in hits
            ],
            reranked=[],
            threshold=0.8,
        )


class HubLeafCageTest(unittest.TestCase):
    def test_cages_to_hub_children(self) -> None:
        parents = ParentIndex(
            child_to_parents={
                "leaf-a": ("hub-auth",),
                "leaf-b": ("hub-auth",),
                "leaf-x": ("hub-other",),
            },
            parent_names={"hub-auth": "Authentication", "hub-other": "Other"},
            parent_to_children={
                "hub-auth": ("leaf-a", "leaf-b"),
                "hub-other": ("leaf-x",),
            },
        )
        inner = _RecordingRetriever(
            [
                # First (global) pass: hub wins.
                [("hub-auth", 0.9), ("noise", 0.8), ("leaf-x", 0.7)],
                # Second (caged) pass: only hub + its children survive allowlist.
                [
                    ("hub-auth", 0.9),
                    ("leaf-a", 0.85),
                    ("leaf-b", 0.80),
                    ("leaf-x", 0.99),
                    ("noise", 0.95),
                ],
            ]
        )
        retriever = HubLeafCageRetriever(inner, parents, top_hubs=1)
        audit = retriever.retrieve("Section: Authentication\n")
        self.assertEqual(retriever.last_hub_cre_ids, ["hub-auth"])
        self.assertIsNotNone(inner.allowlists[1])
        allowed = set(inner.allowlists[1])  # type: ignore[arg-type]
        self.assertEqual(allowed, {"hub-auth", "leaf-a", "leaf-b"})
        ids = [c.cre_id for c in audit.candidates]
        self.assertIn("leaf-a", ids)
        self.assertNotIn("leaf-x", ids)
        self.assertNotIn("noise", ids)
        self.assertIn("hub-leaf-cage", audit.retriever)

    def test_falls_back_when_cage_empty(self) -> None:
        parents = ParentIndex(
            child_to_parents={},
            parent_to_children={},
        )
        inner = _RecordingRetriever(
            [
                [("orphan", 0.9)],
                [],  # cage miss
            ]
        )
        retriever = HubLeafCageRetriever(inner, parents, top_hubs=1)
        audit = retriever.retrieve("body")
        # Provisional hub = top-1; children empty → cage is still {orphan}.
        # Second call returns empty → fail open to global.
        self.assertEqual([c.cre_id for c in audit.candidates], ["orphan"])
        self.assertIn("miss", audit.retriever)


if __name__ == "__main__":
    unittest.main()
