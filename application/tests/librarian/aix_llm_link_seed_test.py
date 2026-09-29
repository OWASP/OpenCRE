"""Tests for AIX / LLM Top10 Link seeding and B2 gold rebuild helpers."""

import unittest

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.aix_llm_link_seed import (
    AixLlmLinkIndex,
    is_ai_or_llm_chunk,
    normalize_llm_section_id,
    section_id_from_text,
)
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.oie_taxonomy import set_default_taxonomy_index
from application.utils.librarian.prior_caged_retriever import PriorCagedRetriever
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


class NormalizeLlmSectionIdTest(unittest.TestCase):
    def test_strips_year_suffix(self) -> None:
        self.assertEqual(normalize_llm_section_id("LLM01:2025"), "LLM01")
        self.assertEqual(normalize_llm_section_id("llm02"), "LLM02")

    def test_rejects_non_llm(self) -> None:
        self.assertEqual(normalize_llm_section_id("A01"), "")
        self.assertEqual(normalize_llm_section_id(""), "")


class SectionIdFromTextTest(unittest.TestCase):
    def test_source_prefix(self) -> None:
        text = "Source: LLM01\nSection: Prompt Injection\nSection-ID: LLM01\n"
        self.assertEqual(section_id_from_text(text), "LLM01")


class AixLlmLinkIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.idx = AixLlmLinkIndex(
            section_to_cres={"LLM01": ("uuid-direct", "uuid-indirect")},
            aix_cre_ids=frozenset({"uuid-aix-1", "uuid-aix-2"}),
        )

    def test_preferred_for_llm_section(self) -> None:
        problem = ProblemClass("prompt_injection", "ai", section_id="LLM01")
        self.assertEqual(
            self.idx.preferred_for(problem, "Section-ID: LLM01\n"),
            ["uuid-direct", "uuid-indirect"],
        )

    def test_prior_extra_for_ai_family(self) -> None:
        problem = ProblemClass("prompt_injection", "ai", section_id="LLM01")
        extra = self.idx.prior_extra_for(problem)
        self.assertEqual(extra, frozenset({"uuid-aix-1", "uuid-aix-2"}))

    def test_skips_non_ai(self) -> None:
        problem = ProblemClass("authentication", "auth", section_id="A07")
        self.assertEqual(self.idx.preferred_for(problem), [])
        self.assertEqual(self.idx.prior_extra_for(problem), frozenset())

    def test_is_ai_from_section_id_alone(self) -> None:
        problem = ProblemClass("general", "appsec", section_id="")
        self.assertTrue(
            is_ai_or_llm_chunk(problem, "Source: LLM04\nSection-ID: LLM04\n")
        )


class PriorCagedWithAixLlmTest(unittest.TestCase):
    def setUp(self) -> None:
        set_default_taxonomy_index(fixture_taxonomy_index())

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_llm_links_lead_preferred_and_cage(self) -> None:
        seen = {}

        class Inner:
            def retrieve(self, text, *, allowlist=None):
                seen["allowlist"] = set(allowlist or [])
                return RetrievalAudit(
                    retriever="stub",
                    candidates=[
                        CreCandidate(cre_id="uuid-direct", score_vector=0.5),
                        CreCandidate(cre_id="noise", score_vector=0.9),
                    ],
                    reranked=[],
                    threshold=0.8,
                )

        prior = CrePriorIndex(
            class_to_cres={"prompt_injection": frozenset({"uuid-direct"})},
            thin_class=8,
            min_prior=1,
        )
        aix = AixLlmLinkIndex(
            section_to_cres={"LLM01": ("uuid-direct",)},
            aix_cre_ids=frozenset({"uuid-aix"}),
        )
        caged = PriorCagedRetriever(Inner(), prior, aix_llm_links=aix)
        text = "Source: LLM01\nSection-ID: LLM01\nSection: Prompt Injection\n"
        audit = caged.retrieve(text)
        self.assertIn("uuid-direct", seen["allowlist"])
        self.assertIn("uuid-aix", seen["allowlist"])
        self.assertEqual(caged.last_preferred_cre_ids[0], "uuid-direct")
        self.assertIn("hub-links", audit.retriever)
        self.assertIn("hub-bag", audit.retriever)
        self.assertEqual(audit.candidates[0].cre_id, "uuid-direct")


class GoldRebuildHelpersTest(unittest.TestCase):
    def test_build_gold_rows_marks_gaps(self) -> None:
        # Import from script path via runpy-style relative — keep pure helper copy.
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "oie_owasp_eval"
            / "rebuild_b2_llm_gold_from_hub.py"
        )
        spec = importlib.util.spec_from_file_location("rebuild_b2_llm_gold", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        hub = {
            "LLM01": ["686-110", "012-625"],
            "LLM03": ["701-654"],
        }
        existing = {
            "LLM01": {
                "section": "Prompt Injection",
                "hyperlink": "https://example.test/llm01",
            }
        }
        rows, gaps = mod.build_gold_rows(hub, existing=existing)
        self.assertEqual(len(rows), 10)
        llm01 = next(r for r in rows if r["section_id"] == "LLM01")
        self.assertEqual(llm01["cre_ids"], ["012-625", "686-110"])
        self.assertEqual(llm01["hyperlink"], "https://example.test/llm01")
        self.assertIn("LLM06", gaps)
        self.assertIn("LLM09", gaps)
        empty = next(r for r in rows if r["section_id"] == "LLM06")
        self.assertEqual(empty["cre_ids"], [])


if __name__ == "__main__":
    unittest.main()
