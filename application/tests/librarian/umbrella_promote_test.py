"""Tests for exact-name latch and umbrella parent promotion."""

from __future__ import annotations

import unittest

from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.umbrella_promote import (
    ExactNameIndex,
    ParentIndex,
    merge_preferred,
)


class ExactNameIndexTest(unittest.TestCase):
    def test_exact_section_title_match(self) -> None:
        idx = ExactNameIndex(
            name_to_cre={
                "cryptography": ("cre-crypto",),
                "error handling": ("cre-err",),
            }
        )
        hits = idx.match_for_text(
            "Section: Cryptography\nSection-ID: A04\nBody about AES.\n"
        )
        self.assertEqual(hits, ["cre-crypto"])

    def test_heading_path_uses_leaf(self) -> None:
        idx = ExactNameIndex(name_to_cre={"authentication": ("cre-auth",)})
        hits = idx.match_for_text("Section: Auth > Authentication\n")
        self.assertEqual(hits, ["cre-auth"])


class ParentIndexTest(unittest.TestCase):
    def test_promotes_shared_parent(self) -> None:
        idx = ParentIndex(
            child_to_parents={
                "leaf-a": ("parent-auth",),
                "leaf-b": ("parent-auth",),
                "leaf-c": ("other",),
            }
        )
        out = idx.promote_for_shortlist(["leaf-a", "leaf-b", "leaf-c", "noise"])
        self.assertEqual(out[:1], ["parent-auth"])
        self.assertNotIn("other", out)


class MergePreferredTest(unittest.TestCase):
    def test_earlier_groups_win(self) -> None:
        self.assertEqual(
            merge_preferred(["a"], ["a", "b"], ["c"], limit=3),
            ["a", "b", "c"],
        )


class PriorWithExactAndUmbrellaTest(unittest.TestCase):
    def test_exact_name_leads_preferred_and_candidates(self) -> None:
        class Inner:
            def retrieve(self, text, *, allowlist=None):
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="noise", score_vector=0.99),
                        CreCandidate(cre_id="cre-crypto", score_vector=0.4),
                        CreCandidate(cre_id="other", score_vector=0.5),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "cryptography": frozenset({f"c{i}" for i in range(10)} | {"cre-crypto"}),
            },
            thin_class=8,
        )
        exact = ExactNameIndex(name_to_cre={"cryptography": ("cre-crypto",)})
        caged = PriorCagedRetriever(
            Inner(), prior, exact_name_index=exact
        )
        audit = caged.retrieve("Section: Cryptography\nSection-ID: A04\n")
        self.assertEqual(caged.last_preferred_cre_ids[:1], ["cre-crypto"])
        self.assertEqual(audit.candidates[0].cre_id, "cre-crypto")
        self.assertIn("exact-name", audit.retriever)

    def test_umbrella_parent_promoted(self) -> None:
        class Inner:
            def retrieve(self, text, *, allowlist=None):
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="leaf-a", score_vector=0.9),
                        CreCandidate(cre_id="leaf-b", score_vector=0.85),
                        CreCandidate(cre_id="noise", score_vector=0.8),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset(
                    {f"a{i}" for i in range(10)} | {"leaf-a", "leaf-b"}
                ),
            },
            thin_class=8,
        )
        parents = ParentIndex(
            child_to_parents={"leaf-a": ("parent-auth",), "leaf-b": ("parent-auth",)}
        )
        caged = PriorCagedRetriever(Inner(), prior, parent_index=parents)
        audit = caged.retrieve(
            "Source: A07.txt\nSection: Authentication Failures\n"
        )
        self.assertIn("parent-auth", caged.last_preferred_cre_ids)
        self.assertIn("umbrella", audit.retriever)


if __name__ == "__main__":
    unittest.main()
