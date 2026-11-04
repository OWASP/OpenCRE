"""Integration-style cutover: comprehension/router call LI/LC entrypoints when flagged."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock


class FlagsAliasTest(unittest.TestCase):
    def test_parity_alias_can_force_li_retrieve_off(self) -> None:
        from application.utils.comprehension import flags

        with mock.patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("OWASP_CX_") or k.startswith("CRE_RAG_PARITY_"):
                    os.environ.pop(k, None)
            self.assertTrue(flags.on("LI_RETRIEVE"))  # DEFAULT_ON (TASK-14.8)
            os.environ["CRE_RAG_PARITY_LI_RETRIEVE"] = "0"
            self.assertFalse(flags.on("LI_RETRIEVE"))
            os.environ.pop("CRE_RAG_PARITY_LI_RETRIEVE")

    def test_keyword_hybrid_flag_removed(self) -> None:
        """Ask-side keyword/FTS HYBRID deleted; LI_HYBRID env must not disable LI."""
        from application.utils.comprehension import flags

        self.assertNotIn("HYBRID", flags.NAMES)
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("OWASP_CX_") or k.startswith("CRE_RAG_PARITY_"):
                    os.environ.pop(k, None)
            os.environ["CRE_RAG_PARITY_LI_HYBRID"] = "1"
            os.environ["OWASP_CX_HYBRID"] = "1"
            self.assertTrue(flags.on("LI_RETRIEVE"))  # still DEFAULT_ON
            self.assertNotIn("HYBRID", flags.active())
            os.environ.pop("CRE_RAG_PARITY_LI_HYBRID", None)
            os.environ.pop("OWASP_CX_HYBRID", None)


class LiRetrieveWiringTest(unittest.TestCase):
    def test_li_queryfusion_fuses_two_lists(self) -> None:
        from application.utils.comprehension.li_retrieve import (
            fuse_rankings_with_llamaindex,
            li_available,
        )

        if not li_available():
            self.skipTest("llama_index not installed")
        hit_a = SimpleNamespace(url="u1", score=0.9)
        hit_b = SimpleNamespace(url="u2", score=0.8)
        out = fuse_rankings_with_llamaindex(
            [[hit_a, hit_b], [hit_b, hit_a]], key=lambda h: h.url
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual({h.url for h in out}, {"u1", "u2"})
        # Both lists rank u* — RRF should keep both; top should be present.
        self.assertIn(out[0].url, {"u1", "u2"})

    def test_li_source_uses_public_queryfusion_not_private_helper(self) -> None:
        from pathlib import Path

        src = Path("application/utils/comprehension/li_retrieve.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QueryFusionRetriever(", src)
        self.assertIn("FUSION_MODES.RECIPROCAL_RANK", src)
        self.assertIn("num_queries=1", src)
        self.assertNotIn("_reciprocal_rerank_fusion(", src)
        self.assertNotIn("object()", src)

    def test_retrieve_module_wires_li_flag_without_keyword_hybrid(self) -> None:
        from pathlib import Path

        src = Path("application/utils/comprehension/retrieve.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("fuse_rankings_with_llamaindex", src)
        self.assertIn('flags.on("LI_RETRIEVE")', src)
        self.assertNotIn('flags.on("HYBRID")', src)
        self.assertNotIn("supplement_with_keyword", src)
        self.assertNotIn("_KW_SQL", src)
        self.assertNotIn("def _keyword(", src)


class LcRouterWiringTest(unittest.TestCase):
    def test_classify_intent_calls_lc_when_regex_clarify(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.router._classify_intent_regex",
                return_value="clarify",
            ):
                with mock.patch(
                    "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                    return_value="project_lookup",
                ) as lc:
                    intent = classify_intent("who is the chapter leader?")
                    self.assertEqual(intent, "project_lookup")
                    lc.assert_called()

    def test_classify_intent_falls_back_without_lc_result(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value=None,
            ):
                # Falls through to regex — empty/garbage still returns a string intent
                intent = classify_intent("how do I mitigate SQL injection in my app")
                self.assertIsInstance(intent, str)
                self.assertTrue(intent)


class CitationsWiringTest(unittest.TestCase):
    def test_synthesize_strips_when_citations_flag_on(self) -> None:
        from application.utils.comprehension.synthesize import synthesize

        def llm(system: str, user: str) -> str:
            return "Cited fact [1]. Uncited fluff sentence."

        hits = [("Source text about passwords and MFA requirements.", ["http://a"])]
        with mock.patch.dict(os.environ, {"OWASP_CX_CITATIONS": "1"}):
            answer, cites = synthesize("q", hits, llm)
        self.assertIn("[1]", answer)
        self.assertNotIn("Uncited fluff", answer)


class ModernRerankWiringTest(unittest.TestCase):
    def test_answer_imports_phase4_when_modern_rerank(self) -> None:
        from pathlib import Path

        src = Path("application/utils/comprehension/answer.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MODERN_RERANK", src)
        self.assertIn("rerank_and_compress", src)


class IngestScriptWiringTest(unittest.TestCase):
    def test_ingest_script_uses_phase2(self) -> None:
        from pathlib import Path

        src = Path("scripts/rag_parity_ingest.py").read_text(encoding="utf-8")
        self.assertIn("ingest_path_to_writer", src)
        self.assertIn("load_flags", src)


if __name__ == "__main__":
    unittest.main()
