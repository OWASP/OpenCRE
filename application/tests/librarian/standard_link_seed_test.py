"""Tests for generalized standard Link seeding."""

import unittest

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.oie_taxonomy import set_default_taxonomy_index
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.standard_link_seed import (
    EditionLinkMap,
    StandardLinkIndex,
    normalize_section_id,
    section_id_from_text,
)


class NormalizeSectionIdTest(unittest.TestCase):
    def test_strips_year_and_families(self) -> None:
        self.assertEqual(normalize_section_id("LLM01:2025"), "LLM01")
        self.assertEqual(normalize_section_id("K03"), "K03")
        self.assertEqual(normalize_section_id("A01"), "A01")
        self.assertEqual(normalize_section_id("API4"), "API4")


class SectionIdFromTextTest(unittest.TestCase):
    def test_k8s_source(self) -> None:
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\nSource: K02\nSection-ID: K02\n"
        )
        self.assertEqual(section_id_from_text(text), "K02")


class StandardLinkIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.idx = StandardLinkIndex(
            editions={
                "k8s_top10": (
                    EditionLinkMap(
                        year=2025, section_to_cres={"K01": ("uuid-k1", "uuid-k2")}
                    ),
                ),
                "llm_top10": (
                    EditionLinkMap(year=2025, section_to_cres={"LLM01": ("uuid-llm",)}),
                ),
            },
            bags={"ai_exchange": frozenset({"uuid-aix"})},
        )

    def test_k8s_preferred(self) -> None:
        problem = ProblemClass("general", "appsec", section_id="K01")
        text = "Standard: owasp_kubernetes_top10_2025.json\nSection-ID: K01\n"
        self.assertEqual(
            self.idx.preferred_for(problem, text),
            ["uuid-k1", "uuid-k2"],
        )

    def test_year_scopes_k8s_editions(self) -> None:
        idx = StandardLinkIndex(
            editions={
                "k8s_top10": (
                    EditionLinkMap(
                        year=2022, section_to_cres={"K06": ("uuid-auth-2022",)}
                    ),
                    EditionLinkMap(
                        year=2025, section_to_cres={"K06": ("uuid-exposed-2025",)}
                    ),
                ),
            }
        )
        problem = ProblemClass("general", "appsec", section_id="K06")
        text_2022 = (
            "Standard: OWASP Kubernetes Top 10 2022\n"
            "Version: 2022\n"
            "Section-ID: K06\n"
        )
        text_bare = "Source: K06\nSection-ID: K06\n"  # year=0 → all editions
        self.assertEqual(idx.preferred_for(problem, text_2022), ["uuid-auth-2022"])
        both = idx.preferred_for(problem, text_bare)
        self.assertEqual(set(both), {"uuid-auth-2022", "uuid-exposed-2025"})

    def test_versioned_year_without_edition_skips_same_sid_inherit(self) -> None:
        """New year with no hub Links must not copy older same section_id.

        Top10/K8s reshuffle topics across editions; blind A02→A02 seeds the wrong
        CRE. Title-aware ``edition_remap`` (PriorCagedRetriever) covers cold
        editions instead.
        """
        idx = StandardLinkIndex(
            editions={
                "owasp_top10": (
                    EditionLinkMap(
                        year=2021,
                        section_to_cres={
                            "A01": ("uuid-access-2021",),
                            "A02": ("uuid-crypto-2021",),
                        },
                    ),
                ),
            }
        )
        problem = ProblemClass("general", "appsec", section_id="A02")
        text_2025 = (
            "Standard: OWASP Top 10 2025\n"
            "Version: 2025\n"
            "Section: Security Misconfiguration\n"
            "Section-ID: A02\n"
        )
        self.assertEqual(idx.preferred_for(problem, text_2025), [])

    def test_exact_year_wins_over_predecessor(self) -> None:
        idx = StandardLinkIndex(
            editions={
                "k8s_top10": (
                    EditionLinkMap(
                        year=2022, section_to_cres={"K06": ("uuid-auth-2022",)}
                    ),
                    EditionLinkMap(
                        year=2025, section_to_cres={"K06": ("uuid-exposed-2025",)}
                    ),
                ),
            }
        )
        problem = ProblemClass("general", "appsec", section_id="K06")
        text_2025 = (
            "Standard: OWASP Kubernetes Top 10 2025\n"
            "Version: 2025\n"
            "Section-ID: K06\n"
        )
        self.assertEqual(idx.preferred_for(problem, text_2025), ["uuid-exposed-2025"])

    def test_llm_bag(self) -> None:
        problem = ProblemClass("prompt_injection", "ai", section_id="LLM01")
        self.assertEqual(
            self.idx.prior_extra_for(problem, "Section-ID: LLM01\n"),
            frozenset({"uuid-aix"}),
        )

    def test_skips_unrelated_family(self) -> None:
        problem = ProblemClass("authentication", "auth", section_id="A07")
        self.assertEqual(self.idx.preferred_for(problem, "Section-ID: A07\n"), [])


class PriorCagedWithStandardLinksTest(unittest.TestCase):
    def setUp(self) -> None:
        set_default_taxonomy_index(fixture_taxonomy_index())

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_hub_links_lead_preferred(self) -> None:
        seen = {}

        class Inner:
            def retrieve(self, text, *, allowlist=None):
                seen["allowlist"] = set(allowlist or [])
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="uuid-k1", score_vector=0.5),
                        CreCandidate(cre_id="uuid-other", score_vector=0.9),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={"general": frozenset({"uuid-k1"})},
            thin_class=8,
            min_prior=1,
        )
        idx = StandardLinkIndex(
            editions={
                "k8s_top10": (
                    EditionLinkMap(year=2025, section_to_cres={"K01": ("uuid-k1",)}),
                ),
            },
        )
        retriever = PriorCagedRetriever(
            Inner(),
            prior,
            standard_links=idx,
        )
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Source: K01\n"
            "Section-ID: K01\n"
            "Section: Insecure Workload Configurations\n"
        )
        audit = retriever.retrieve(text)
        self.assertIn("uuid-k1", retriever.last_preferred_cre_ids)
        self.assertIn("uuid-k1", seen["allowlist"])
        self.assertIn("hub-links", audit.retriever)
        self.assertEqual(audit.candidates[0].cre_id, "uuid-k1")


if __name__ == "__main__":
    unittest.main()
