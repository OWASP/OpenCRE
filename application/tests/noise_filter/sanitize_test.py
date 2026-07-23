"""Tests for application.utils.noise_filter.sanitize.

Uses unittest to match the project-wide discovery pattern.

Coverage groups:
    1. PipelineTests     -- each sanitization rule applied in isolation
    2. IdempotencyTests  -- sanitize(sanitize(x)) == sanitize(x) for all classes of input
    3. EdgeCaseTests     -- empty, all-whitespace, raises on collapse-to-empty
    4. StripHtmlTests    -- public strip_html() helper
"""

from __future__ import annotations

import unittest

from application.utils.noise_filter.sanitize import sanitize_text, strip_html


# --- 1. Pipeline rules in isolation --------------------------------------


class PipelineTests(unittest.TestCase):

    def test_strips_null_bytes(self) -> None:
        self.assertEqual(sanitize_text("hello\x00world"), "hello world")

    def test_nfc_normalizes_decomposed(self) -> None:
        # "é" can be a single codepoint U+00E9 (NFC) or e + combining acute (NFD).
        decomposed = "café"  # e + combining acute -> "café"
        composed = "café"
        self.assertEqual(sanitize_text(decomposed), composed)

    def test_strips_zero_width_characters(self) -> None:
        # U+200B ZWSP between every char of "hello".
        text = "h\u200be\u200bl\u200bl\u200bo"
        self.assertEqual(sanitize_text(text), "hello")

    def test_strips_html_tags(self) -> None:
        self.assertEqual(
            sanitize_text("<p>Use <b>parameterized</b> queries.</p>"),
            "Use parameterized queries.",
        )

    def test_decodes_html_entities_before_stripping(self) -> None:
        # &lt;script&gt; -> <script> -> stripped. The original literal text should not survive.
        self.assertEqual(
            sanitize_text("Beware: &lt;script&gt;alert(1)&lt;/script&gt;"),
            "Beware: alert(1)",
        )

    def test_replaces_pdf_ligatures(self) -> None:
        self.assertEqual(
            sanitize_text("oﬃcial conﬁguration ﬂag for waﬄes"),
            "official configuration flag for waffles",
        )

    def test_replaces_compound_ligatures_first(self) -> None:
        # ﬄ must be replaced as "ffl" not partially as "fl" + leftover.
        self.assertEqual(sanitize_text("baﬄed"), "baffled")
        # ﬃ same.
        self.assertEqual(sanitize_text("oﬃcer"), "officer")

    def test_rejoins_hyphenated_linebreaks(self) -> None:
        # "encryp-\ntion" from PDF should rejoin to "encryption".
        self.assertEqual(
            sanitize_text("This describes encryp-\ntion at rest."),
            "This describes encryption at rest.",
        )

    def test_preserves_interior_paragraph_breaks(self) -> None:
        """KEY difference vs TRACT: do NOT collapse newlines."""
        text = "Paragraph one.\n\nParagraph two."
        self.assertEqual(sanitize_text(text), "Paragraph one.\n\nParagraph two.")

    def test_preserves_interior_runs_of_spaces(self) -> None:
        """Module A's normalization decides interior spacing; we don't second-guess."""
        text = "code  with  double  spaces"
        self.assertEqual(sanitize_text(text), "code  with  double  spaces")

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        self.assertEqual(sanitize_text("   hello   "), "hello")
        self.assertEqual(sanitize_text("\n\n  hello  \n\n"), "hello")


# --- 2. Idempotency -------------------------------------------------------


class IdempotencyTests(unittest.TestCase):

    def _assert_idempotent(self, text: str) -> None:
        once = sanitize_text(text)
        twice = sanitize_text(once)
        self.assertEqual(once, twice)

    def test_idempotent_on_clean_text(self) -> None:
        self._assert_idempotent("Plain ASCII security text.")

    def test_idempotent_on_dirty_text_with_ligatures(self) -> None:
        self._assert_idempotent("oﬃcial conﬁguration")

    def test_idempotent_on_dirty_text_with_html(self) -> None:
        self._assert_idempotent("<p>Use <b>MFA</b> for auth.</p>")

    def test_idempotent_on_dirty_text_with_zero_width(self) -> None:
        self._assert_idempotent("h\u200be\u200bl\u200bl\u200bo")

    def test_idempotent_on_multiline_text(self) -> None:
        self._assert_idempotent("Line one.\n\nLine two.\n\nLine three.")

    def test_idempotent_on_already_normalized_module_a_output(self) -> None:
        """A clean record from Module A should be a no-op through sanitize."""
        # NFC, no ligatures, no zero-width, plain ASCII -- typical Module A output.
        clean = "## Mitigation\n\nUse parameterized queries to prevent SQL injection."
        self.assertEqual(sanitize_text(clean), clean)


# --- 3. Edge cases --------------------------------------------------------


class EdgeCaseTests(unittest.TestCase):

    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(sanitize_text(""), "")

    def test_all_whitespace_raises(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_text("   \n\n\t\t   ")

    def test_html_that_strips_to_empty_raises(self) -> None:
        # Only HTML tags + entities that decode to whitespace -> after strip, empty.
        with self.assertRaises(ValueError):
            sanitize_text("<p></p><br/>&nbsp;")

    def test_null_bytes_only_raises(self) -> None:
        # Nulls become spaces, then strip removes them all.
        with self.assertRaises(ValueError):
            sanitize_text("\x00\x00\x00")


# --- 4. strip_html public helper ----------------------------------------


class StripHtmlTests(unittest.TestCase):

    def test_strips_simple_tags(self) -> None:
        self.assertEqual(strip_html("<p>Hello</p>"), "Hello")

    def test_strips_self_closing_tags(self) -> None:
        self.assertEqual(strip_html("Line one<br/>Line two"), "Line oneLine two")

    def test_handles_attributes(self) -> None:
        self.assertEqual(strip_html('<a href="x.com">link</a>'), "link")

    def test_decodes_entities_then_strips(self) -> None:
        # &lt;b&gt; decodes to <b>, which then gets stripped.
        self.assertEqual(strip_html("Hello &lt;b&gt;world&lt;/b&gt;"), "Hello world")

    def test_passes_through_plain_text(self) -> None:
        self.assertEqual(strip_html("just plain text"), "just plain text")


if __name__ == "__main__":
    unittest.main()
