"""Tests for cross-standard control-name seeding and preferred-first helpers."""

from __future__ import annotations

import unittest

from application.utils.librarian.control_name_seed import (
    ControlNameIndex,
    prefer_audit_ids,
    prefer_ids_first,
    section_title_from_text,
)
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


class SectionTitleTest(unittest.TestCase):
    def test_reads_section_line(self) -> None:
        text = "Source: A01.txt\nSection: Broken Access Control\nSection-ID: A01\n"
        self.assertEqual(section_title_from_text(text), "Broken Access Control")


class ControlNameIndexTest(unittest.TestCase):
    def test_seed_matches_overlapping_title(self) -> None:
        index = ControlNameIndex(
            entries=(
                (
                    frozenset({"access", "control", "broken"}),
                    "Broken Access Control",
                    ("cre-access",),
                ),
                (
                    frozenset({"cryptographic", "failures"}),
                    "Cryptographic Failures",
                    ("cre-crypto",),
                ),
            ),
            min_score=0.2,
            top_k=5,
        )
        hits = index.seed_for_text("Section: Broken Access Control\nSection-ID: A01\n")
        self.assertEqual(hits, ["cre-access"])
        self.assertNotIn("cre-crypto", hits)


class PreferIdsFirstTest(unittest.TestCase):
    def test_preferred_leads_then_ordered(self) -> None:
        out = prefer_ids_first(
            ["edition-a", "edition-b", "name-c"],
            ["vec-1", "edition-a", "vec-2"],
            limit=4,
            lead=2,
        )
        self.assertEqual(out[:2], ["edition-a", "edition-b"])
        self.assertEqual(out[2:], ["vec-1", "vec-2"])

    def test_prefer_audit_reorders_reranked_and_candidates(self) -> None:
        audit = RetrievalAudit(
            retriever="stub",
            candidates=[
                CreCandidate(cre_id="noise", score_vector=0.99),
                CreCandidate(cre_id="gold", score_vector=0.5),
            ],
            reranked=[
                CreCandidate(cre_id="noise", score_rerank=0.9),
                CreCandidate(cre_id="gold", score_rerank=0.1),
            ],
            threshold=0.5,
        )
        out = prefer_audit_ids(audit, ["gold", "other"], lead=2)
        self.assertEqual([c.cre_id for c in out.candidates[:1]], ["gold"])
        self.assertEqual([c.cre_id for c in out.reranked[:1]], ["gold"])

    def test_prefer_audit_injects_preferred_from_candidates_into_reranked(self) -> None:
        """CE top-N may drop preferred; B2 still needs them in reranked[:2]."""
        audit = RetrievalAudit(
            retriever="stub",
            candidates=[
                CreCandidate(cre_id="noise", score_vector=0.99),
                CreCandidate(cre_id="gold", cre_name="Gold", score_vector=0.5),
            ],
            reranked=[
                CreCandidate(cre_id="noise", score_rerank=0.9),
            ],
            threshold=0.5,
        )
        # Default: reorder-only (no inject) — gold stays out of reranked.
        plain = prefer_audit_ids(audit, ["gold"], lead=2)
        self.assertEqual([c.cre_id for c in plain.reranked], ["noise"])
        # Judge path: inject CE-dropped preferred from candidates.
        out = prefer_audit_ids(audit, ["gold"], lead=2, inject_missing=True)
        self.assertEqual(out.reranked[0].cre_id, "gold")
        self.assertIsNotNone(out.reranked[0].score_rerank)
        self.assertEqual(out.reranked[1].cre_id, "noise")


class PriorPreferredSeedTest(unittest.TestCase):
    def test_control_name_seeds_allowlist_and_preferred(self) -> None:
        seen = {}

        class Inner:
            def retrieve(self, text, *, allowlist=None):
                seen["allowlist"] = set(allowlist or [])
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="auth-1", score_vector=0.5),
                        CreCandidate(cre_id="name-hit", score_vector=0.4),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset({f"a{i}" for i in range(10)}),
            },
            thin_class=8,
        )
        index = ControlNameIndex(
            entries=(
                (
                    frozenset({"authentication", "failures"}),
                    "Authentication Failures",
                    ("name-hit",),
                ),
            ),
            min_score=0.2,
        )
        caged = PriorCagedRetriever(Inner(), prior, control_name_index=index)
        audit = caged.retrieve("Source: A07.txt\nSection: Authentication Failures\n")
        self.assertIn("name-hit", seen["allowlist"])
        self.assertEqual(caged.last_preferred_cre_ids[:1], ["name-hit"])
        self.assertEqual(audit.candidates[0].cre_id, "name-hit")


if __name__ == "__main__":
    unittest.main()
