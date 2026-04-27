"""Unit tests for smart embedding excerpt alignment (no network, no LLM)."""

import unittest

from application.defs import cre_defs
from application.prompt_client import embed_alignment


class _FakeAlignClient:
    def __init__(self, payload: dict):
        self._payload = payload

    def align_embedding_span_json(self, _system: str, _user: str) -> dict:
        return self._payload


class EmbedAlignmentTest(unittest.TestCase):
    def test_schema_rejects_invalid_alignment_payload(self):
        html = """
        <html><body><main id="main">
          <div id="ai-program"><p>Alpha program body text here with more words to pass excerpt length.</p></div>
        </main></body></html>
        """
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="AI Program",
            sectionID="aiprogram",
            subsection="",
            hyperlink="https://owaspai.org/go/aiprogram/",
        )
        client = _FakeAlignClient(
            {
                "start_bid": "oops",
                "end_bid": "b0",
                "suggested_fragment": "ai-program",
                "confidence": 1.2,
                "should_fallback_full_page": False,
                "rationale": "bad payload",
            }
        )
        out = embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="full page text",
            node=node,
            ai_client=client,
            mode="on",
            page_cache_key="https://owaspai.org/go/aiprogram",
            alignment_cache={},
            confidence_threshold=0.5,
        )
        self.assertFalse(out.used_excerpt)
        self.assertEqual(out.embed_plain_text, "full page text")
        self.assertIn("llm_error:invalid alignment payload:", out.rationale)

    def test_build_blocks_collects_ids(self):
        html = """
        <html><body><main id="main">
          <div id="ai-program"><h2>AI Program</h2><p>Body one longer text here.</p></div>
          <div id="ai-transparency"><h2>Transparency</h2><p>Body two longer text here.</p></div>
        </main></body></html>
        """
        blocks, frags = embed_alignment.build_blocks_from_html(html)
        self.assertGreaterEqual(len(blocks), 2)
        ids = {b["fragment"] for b in blocks}
        self.assertIn("ai-program", ids)
        self.assertIn("ai-transparency", ids)
        self.assertIn("ai-program", frags)

    def test_run_smart_extract_concat_excerpt_and_fragment(self):
        html = """
        <html><body><main id="main">
          <div id="ai-program"><h2>AI Program</h2><p>Alpha control text for program.</p></div>
          <div id="other-section"><p>Unrelated bulk content unrelated unrelated.</p></div>
        </main></body></html>
        """
        full_clean = "Alpha control text for program. Unrelated bulk content unrelated unrelated."
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="AI Program",
            sectionID="aiprogram",
            subsection="",
            hyperlink="https://owaspai.org/go/aiprogram/",
        )
        client = _FakeAlignClient(
            {
                "start_bid": "b0",
                "end_bid": "b0",
                "suggested_fragment": "ai-program",
                "confidence": 0.95,
                "should_fallback_full_page": False,
                "rationale": "Heading matches section",
            }
        )
        cache: dict = {}
        out = embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text=full_clean,
            node=node,
            ai_client=client,
            mode="on",
            page_cache_key="https://owaspai.org/go/aiprogram",
            alignment_cache=cache,
            confidence_threshold=0.5,
        )
        self.assertTrue(out.used_excerpt)
        self.assertIn("Alpha control", out.embed_plain_text)
        self.assertIn("#ai-program", out.resolved_embeddings_url)
        self.assertEqual(len(cache), 1)

    def test_rejects_unknown_fragment(self):
        html = """
        <html><body><main id="main">
          <div id="ai-program"><p>Alpha program body text here with more words to pass excerpt length.</p></div>
        </main></body></html>
        """
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="AI Program",
            sectionID="aiprogram",
            subsection="",
            hyperlink="https://owaspai.org/go/aiprogram/",
        )
        client = _FakeAlignClient(
            {
                "start_bid": "b0",
                "end_bid": "b0",
                "suggested_fragment": "does-not-exist",
                "confidence": 0.99,
                "should_fallback_full_page": False,
                "rationale": "bad",
            }
        )
        out = embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="full page",
            node=node,
            ai_client=client,
            mode="on",
            page_cache_key="https://owaspai.org/go/aiprogram",
            alignment_cache={},
            confidence_threshold=0.5,
        )
        self.assertTrue(out.used_excerpt)
        self.assertNotIn("#", out.resolved_embeddings_url)

    def test_shadow_keeps_full_page_embed_text(self):
        html = """
        <html><body><main id="main">
          <div id="x"><p>Shadow section body with enough characters for excerpt threshold.</p></div>
        </main></body></html>
        """
        node = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="Y",
            sectionID="z",
            subsection="",
            hyperlink="https://example.com/p",
        )
        client = _FakeAlignClient(
            {
                "start_bid": "b0",
                "end_bid": "b0",
                "suggested_fragment": "x",
                "confidence": 0.99,
                "should_fallback_full_page": False,
                "rationale": "ok",
            }
        )
        out = embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="FULL PAGE TEXT",
            node=node,
            ai_client=client,
            mode="shadow",
            page_cache_key="https://example.com/p",
            alignment_cache={},
            confidence_threshold=0.5,
        )
        self.assertEqual(out.embed_plain_text, "FULL PAGE TEXT")
        self.assertFalse(out.used_excerpt)
        self.assertTrue(out.shadow_only)

    def test_alignment_cache_per_section_key(self):
        html = """
        <html><body><main id="main">
          <div id="a"><p>Section alpha content with enough characters.</p></div>
          <div id="b"><p>Section beta content with enough characters.</p></div>
        </main></body></html>
        """
        calls = {"n": 0}

        class CountingClient:
            def align_embedding_span_json(self, _s, _u):
                calls["n"] += 1
                return {
                    "start_bid": "b0",
                    "end_bid": "b0",
                    "suggested_fragment": "a",
                    "confidence": 0.9,
                    "should_fallback_full_page": False,
                    "rationale": "",
                }

        client = CountingClient()
        cache: dict = {}
        page_key = "https://example.com/doc"
        node1 = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="Sec1",
            sectionID="1",
            subsection="",
            hyperlink="https://example.com/doc",
        )
        node2 = cre_defs.Standard(
            name="OWASP AI Exchange",
            section="Sec2",
            sectionID="2",
            subsection="",
            hyperlink="https://example.com/doc",
        )
        embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="aaa bbb",
            node=node1,
            ai_client=client,
            mode="on",
            page_cache_key=page_key,
            alignment_cache=cache,
            confidence_threshold=0.5,
        )
        embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="aaa bbb",
            node=node1,
            ai_client=client,
            mode="on",
            page_cache_key=page_key,
            alignment_cache=cache,
            confidence_threshold=0.5,
        )
        self.assertEqual(calls["n"], 1)
        embed_alignment.run_smart_extract(
            html=html,
            full_cleaned_body_text="aaa bbb",
            node=node2,
            ai_client=client,
            mode="on",
            page_cache_key=page_key,
            alignment_cache=cache,
            confidence_threshold=0.5,
        )
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
