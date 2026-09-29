"""Tests for neighbor-standard transfer (path B levers 2–4)."""

import unittest

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.neighbor_transfer import (
    NeighborSectionHit,
    NeighborTransferIndex,
    detect_standard_family,
)
from application.utils.librarian.oie_taxonomy import set_default_taxonomy_index
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


class DetectStandardFamilyTest(unittest.TestCase):
    def test_k8s_from_standard_line(self) -> None:
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Source: K02\n"
            "Section-ID: K02\n"
            "Section: Overly Permissive Authorization Configurations\n"
        )
        self.assertEqual(detect_standard_family(text), "owasp_k8s_top10")

    def test_api_from_section_id(self) -> None:
        text = "Standard: owasp_api_top10_2023.json\nSection-ID: API1\n"
        self.assertEqual(detect_standard_family(text), "owasp_api_top10")


class NeighborTransferIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.idx = NeighborTransferIndex(
            bags={
                "owasp_k8s_top10": frozenset(
                    {"uuid-ccm-auth", "uuid-ccm-net", "uuid-noise", "uuid-extra"}
                ),
            },
            sections={
                "owasp_k8s_top10": (
                    NeighborSectionHit(
                        key="CCM|IAM",
                        title="Identity and Access Management",
                        cre_ids=("uuid-ccm-auth",),
                        aliases=("overly permissive authorization", "rbac"),
                    ),
                    NeighborSectionHit(
                        key="CCM|IVS-06",
                        title="Segmentation and Segregation",
                        cre_ids=("uuid-ccm-net",),
                        aliases=("missing network segmentation controls",),
                    ),
                    NeighborSectionHit(
                        key="CCM|LOG",
                        title="Logging and Monitoring",
                        cre_ids=("uuid-ccm-log",),
                    ),
                ),
            },
        )

    def test_narrow_prior_not_full_bag(self) -> None:
        problem = ProblemClass("general", "appsec", section_id="K02")
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Section-ID: K02\n"
            "Section: Overly Permissive Authorization Configurations\n"
        )
        narrow, title_pref, topic_pref, full = self.idx.apply(problem, text)
        self.assertIn("uuid-noise", full)
        self.assertNotIn("uuid-noise", narrow)
        self.assertIn("uuid-ccm-auth", narrow)
        self.assertTrue(title_pref or topic_pref)

    def test_alias_helps_title_match(self) -> None:
        problem = ProblemClass("general", "appsec", section_id="K05")
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Section-ID: K05\n"
            "Section: Missing Network Segmentation Controls\n"
        )
        _n, title_pref, topic_pref, _f = self.idx.apply(problem, text)
        self.assertIn("uuid-ccm-net", title_pref + topic_pref)

    def test_llm_topic_remap(self) -> None:
        def llm(_system: str, user: str) -> str:
            self.assertIn("related_sections", user)
            return '{"K02": ["CCM|IAM"]}'

        idx = NeighborTransferIndex(
            bags={"owasp_k8s_top10": frozenset({"uuid-ccm-auth"})},
            sections={
                "owasp_k8s_top10": (
                    NeighborSectionHit(
                        key="CCM|IAM",
                        title="Identity and Access Management",
                        cre_ids=("uuid-ccm-auth",),
                    ),
                    NeighborSectionHit(
                        key="CCM|LOG",
                        title="Logging and Monitoring",
                        cre_ids=("uuid-ccm-log",),
                    ),
                ),
            },
            llm_fn=llm,
            heuristic_only_families=frozenset(),
            pin_require_title_overlap=False,
        )
        problem = ProblemClass("general", "appsec", section_id="K02")
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Section-ID: K02\n"
            "Section: Overly Permissive Authorization Configurations\n"
        )
        _n, _t, topic, _f = idx.apply(problem, text)
        self.assertIn("uuid-ccm-auth", topic)

    def test_aisvs_neighbor_transfer_disabled(self) -> None:
        idx = NeighborTransferIndex(
            bags={"owasp_aisvs": frozenset({"uuid-aix"})},
            sections={
                "owasp_aisvs": (
                    NeighborSectionHit(
                        key="AIX|AUTH",
                        title="Authentication",
                        cre_ids=("uuid-aix",),
                    ),
                ),
            },
        )
        problem = ProblemClass("ai", "ai", section_id="AISVS-1.1")
        text = (
            "Standard: owasp_aisvs_1_0.json\n"
            "Version: 1.0\n"
            "Section-ID: AISVS-1.1\n"
            "Section: Authentication\n"
        )
        narrow, title_pref, topic_pref, full = idx.apply(problem, text)
        self.assertEqual(narrow, frozenset())
        self.assertEqual(title_pref, [])
        self.assertEqual(topic_pref, [])
        self.assertEqual(full, frozenset())

    def test_k8s_skips_llm_even_when_injected(self) -> None:
        called = {"n": 0}

        def llm(_system: str, _user: str) -> str:
            called["n"] += 1
            return '{"K02": ["CCM|LOG"]}'

        idx = NeighborTransferIndex(
            bags={"owasp_k8s_top10": frozenset({"uuid-ccm-auth", "uuid-ccm-log"})},
            sections={
                "owasp_k8s_top10": (
                    NeighborSectionHit(
                        key="CCM|IAM",
                        title="Identity and Access Management",
                        cre_ids=("uuid-ccm-auth",),
                        aliases=("overly permissive authorization",),
                    ),
                    NeighborSectionHit(
                        key="CCM|LOG",
                        title="Logging and Monitoring",
                        cre_ids=("uuid-ccm-log",),
                    ),
                ),
            },
            llm_fn=llm,
        )
        problem = ProblemClass("general", "appsec", section_id="K02")
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Section-ID: K02\n"
            "Section: Overly Permissive Authorization Configurations\n"
        )
        _n, title_pref, topic_pref, _f = idx.apply(problem, text)
        self.assertEqual(called["n"], 0)
        self.assertIn("uuid-ccm-auth", title_pref)
        self.assertNotIn("uuid-ccm-log", title_pref + topic_pref)

    def test_topic_pin_requires_title_overlap(self) -> None:
        idx = NeighborTransferIndex(
            bags={"owasp_api_top10": frozenset({"uuid-asvs-auth", "uuid-noise"})},
            sections={
                "owasp_api_top10": (
                    NeighborSectionHit(
                        key="ASVS|V2",
                        title="Authentication",
                        cre_ids=("uuid-asvs-auth",),
                        aliases=("broken object level authorization",),
                    ),
                    NeighborSectionHit(
                        key="ASVS|V14",
                        title="Configuration",
                        cre_ids=("uuid-noise",),
                    ),
                ),
            },
            heuristic_only_families=frozenset(),
            pin_require_title_overlap=True,
        )
        problem = ProblemClass("api", "api", section_id="API1")
        text = (
            "Standard: owasp_api_top10_2023.json\n"
            "Version: 2023\n"
            "Section-ID: API1\n"
            "Section: Broken Object Level Authorization\n"
        )
        narrow, title_pref, topic_pref, _f = idx.apply(problem, text)
        self.assertIn("uuid-asvs-auth", title_pref)
        self.assertIn("uuid-asvs-auth", narrow)
        self.assertNotIn("uuid-noise", narrow)
        self.assertTrue(set(topic_pref).issubset(set(title_pref)))


class PriorCagedNeighborTest(unittest.TestCase):
    def setUp(self) -> None:
        set_default_taxonomy_index(fixture_taxonomy_index())

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_narrow_cage_not_full_bag(self) -> None:
        seen = {}

        class Inner:
            def retrieve(self, text, *, allowlist=None):
                seen["allowlist"] = set(allowlist or [])
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="uuid-ccm-auth", score_vector=0.4),
                        CreCandidate(cre_id="uuid-other", score_vector=0.9),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={"general": frozenset()},
            thin_class=8,
            min_prior=1,
        )
        neighbors = NeighborTransferIndex(
            bags={
                "owasp_k8s_top10": frozenset(
                    {"uuid-ccm-auth", "uuid-ccm-net", "uuid-noise"}
                )
            },
            sections={
                "owasp_k8s_top10": (
                    NeighborSectionHit(
                        key="CCM|IAM",
                        title="Identity Access Management Authorization",
                        cre_ids=("uuid-ccm-auth",),
                        aliases=("overly permissive authorization",),
                    ),
                ),
            },
        )
        retriever = PriorCagedRetriever(Inner(), prior, neighbor_transfer=neighbors)
        text = (
            "Standard: owasp_kubernetes_top10_2025.json\n"
            "Version: 2025\n"
            "Section-ID: K02\n"
            "Section: Overly Permissive Authorization Configurations\n"
        )
        audit = retriever.retrieve(text)
        self.assertIn("uuid-ccm-auth", seen["allowlist"])
        self.assertNotIn("uuid-noise", seen["allowlist"])
        self.assertIn("neighbor-narrow", audit.retriever)
        self.assertIn("uuid-ccm-auth", retriever.last_preferred_cre_ids)


if __name__ == "__main__":
    unittest.main()
