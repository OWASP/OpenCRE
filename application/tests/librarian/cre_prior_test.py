"""Tests for C.0.6 CRE prior + caged retrieval."""

import unittest
from types import SimpleNamespace

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.cre_prior import (
    CrePriorIndex,
    build_cre_prior_index,
    cage_candidates,
)
from application.utils.librarian.oie_taxonomy import set_default_taxonomy_index
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


class CrePriorIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tax = fixture_taxonomy_index()
        set_default_taxonomy_index(self.tax)

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_rich_class_stays_class_only(self) -> None:
        idx = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset({f"a{i}" for i in range(10)}),
            },
            family_to_cres={"auth": frozenset({"z"})},
            thin_class=8,
        )
        prior = idx.prior_for(ProblemClass("authentication", "auth"))
        self.assertEqual(len(prior), 10)
        self.assertNotIn("z", prior)

    def test_thin_class_expands_related(self) -> None:
        idx = CrePriorIndex(
            class_to_cres={
                "object_authz": frozenset({"o1"}),
                "access_control": frozenset({"a1", "a2"}),
            },
            family_to_cres={},
            related_classes=dict(self.tax.related_classes),
            thin_class=8,
            thin_transfer=15,
        )
        prior = idx.prior_for(ProblemClass("object_authz", "access"))
        self.assertIn("o1", prior)
        self.assertIn("a1", prior)

    def test_thin_adds_sibling_transfer(self) -> None:
        idx = CrePriorIndex(
            class_to_cres={"prompt_injection": frozenset({"p1"})},
            family_to_cres={},
            transfer_to_cres={"transfer:ai": frozenset({"ai1", "ai2", "ai3"})},
            related_classes=dict(self.tax.related_classes),
            family_to_transfer=dict(self.tax.family_to_transfer),
            thin_class=8,
            thin_transfer=15,
        )
        prior = idx.prior_for(ProblemClass("prompt_injection", "ai"))
        self.assertIn("p1", prior)
        self.assertIn("ai1", prior)

    def test_family_only_when_class_empty(self) -> None:
        idx = CrePriorIndex(
            class_to_cres={},
            family_to_cres={"auth": frozenset({"a", "b", "c", "d", "e", "f"})},
            min_prior=5,
        )
        prior = idx.prior_for(ProblemClass("authentication", "auth"))
        self.assertEqual(prior, frozenset({"a", "b", "c", "d", "e", "f"}))

    def test_build_from_oie_block_and_transfer(self) -> None:
        rows = [
            SimpleNamespace(
                id="uuid-1",
                external_id="111-111",
                name="AuthN",
                description="unused",
                metadata_json={
                    "oie": {
                        "version": 2,
                        "families": ["auth"],
                        "classes": ["authentication"],
                        "domains": ["application"],
                        "standards": ["ASVS"],
                        "signals": ["transfer:top10"],
                        "transfers": ["transfer:top10"],
                    }
                },
            )
        ]
        idx = build_cre_prior_index(
            cre_rows=rows,
            linked_names_by_cre={"uuid-1": ["OWASP Top 10 2021"]},
            taxonomy=self.tax,
            min_prior=1,
        )
        prior = idx.prior_for(ProblemClass("authentication", "auth"))
        self.assertIn("uuid-1", prior)
        self.assertTrue(idx.transfer_to_cres.get("transfer:top10"))


class CageCandidatesTest(unittest.TestCase):
    def test_strict_filter_keeps_thin_cage(self) -> None:
        cands = [
            CreCandidate(cre_id="keep"),
            CreCandidate(cre_id="drop"),
            CreCandidate(cre_id="keep2"),
        ]
        out = cage_candidates(cands, frozenset({"keep"}))
        self.assertEqual([c.cre_id for c in out], ["keep"])

    def test_empty_cage_stays_empty(self) -> None:
        cands = [CreCandidate(cre_id="a"), CreCandidate(cre_id="b")]
        out = cage_candidates(cands, frozenset({"z"}))
        self.assertEqual(out, [])


class PriorCagedRetrieverTest(unittest.TestCase):
    def setUp(self) -> None:
        set_default_taxonomy_index(fixture_taxonomy_index())

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_rewrites_retriever_name_and_filters_strict(self) -> None:
        class Inner:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="auth-1", score_vector=0.9),
                        CreCandidate(cre_id="noise", score_vector=0.8),
                        CreCandidate(cre_id="auth-2", score_vector=0.7),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset(
                    {
                        "auth-1",
                        "auth-2",
                        "auth-3",
                        "auth-4",
                        "auth-5",
                        "auth-6",
                        "auth-7",
                        "auth-8",
                    }
                ),
            },
            family_to_cres={
                "auth": frozenset({"auth-1", "auth-2", "auth-3", "auth-4", "auth-5"})
            },
            family_to_transfer={"auth": "transfer:top10"},
            thin_class=8,
            min_prior=3,
        )
        caged = PriorCagedRetriever(Inner(), prior)
        text = "Source: A07.txt\nSection-ID: A07\nSection: Authentication Failures\n"
        audit = caged.retrieve(text)
        ids = [c.cre_id for c in audit.candidates]
        # Soft cage: prior hits lead; uncaged cosine hits may remain after.
        self.assertEqual(ids[:2], ["auth-1", "auth-2"])
        self.assertIn("noise", ids)  # soft — not wiped
        self.assertIn("+soft", audit.retriever)

    def test_passes_allowlist_to_inner(self) -> None:
        seen = {}

        class Inner:
            def retrieve(self, text, *, allowlist=None):
                seen["allowlist"] = set(allowlist or [])
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[CreCandidate(cre_id="auth-1", score_vector=0.9)],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset({f"a{i}" for i in range(10)}),
            },
            thin_class=8,
        )
        PriorCagedRetriever(Inner(), prior).retrieve(
            "Source: A07.txt\nSection: Authentication Failures\n"
        )
        self.assertEqual(len(seen["allowlist"]), 10)

    def test_relaxed_fallback_avoids_empty_when_family_hits(self) -> None:
        class Inner:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="fam-hit", score_vector=0.9),
                        CreCandidate(cre_id="noise", score_vector=0.8),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={
                "authentication": frozenset({"missing-a", "missing-b"}),
            },
            family_to_cres={"auth": frozenset({"fam-hit"})},
            transfer_to_cres={},
            family_to_transfer={"auth": "transfer:top10"},
            thin_class=8,
            thin_transfer=15,
            min_prior=1,
        )
        audit = PriorCagedRetriever(Inner(), prior).retrieve(
            "Source: A07.txt\nSection-ID: A07\nSection: Authentication Failures\n"
        )
        ids = [c.cre_id for c in audit.candidates]
        self.assertEqual(ids[0], "fam-hit")  # family prior boosted over noise
        self.assertIn("fam-hit", ids)
        self.assertIn("+soft", audit.retriever)


if __name__ == "__main__":
    unittest.main()
