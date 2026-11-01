"""Intent classifier: no substring traps, no city hardcodes."""

from __future__ import annotations

import unittest

from application.utils.owasp_agent.router import classify_intent


class TestIntentNoSubstringTraps(unittest.TestCase):
    def test_prevent_ssrf_is_cre_not_events(self) -> None:
        self.assertEqual(classify_intent("How do I prevent SSRF?"), "cre_normative")
        self.assertEqual(classify_intent("prevent SSRF"), "cre_normative")

    def test_prevent_xss_still_cre(self) -> None:
        self.assertEqual(classify_intent("How do I prevent XSS?"), "cre_normative")

    def test_real_event_ask_still_events(self) -> None:
        self.assertEqual(
            classify_intent("Are there OWASP events near London?"),
            "events_near",
        )


class TestIntentChapterPhrases(unittest.TestCase):
    def test_what_is_london_chapter(self) -> None:
        self.assertEqual(
            classify_intent("What is the OWASP London chapter?"),
            "chapter_lookup",
        )

    def test_chapter_in_city(self) -> None:
        self.assertEqual(
            classify_intent("Does OWASP have a chapter in Berlin?"),
            "chapter_lookup",
        )

    def test_active_status_any_city_no_hardcode(self) -> None:
        self.assertEqual(
            classify_intent("Is the OWASP Berlin chapter active?"),
            "chapter_lookup",
        )
        self.assertEqual(
            classify_intent("Is the OWASP Tokyo chapter active?"),
            "chapter_lookup",
        )

    def test_bare_chapter_word_is_not_enough_for_meta_events(self) -> None:
        # Must not route normative security asks via a stray "chapter" token.
        self.assertNotEqual(
            classify_intent("How do I prevent SSRF in my chapter of the handbook?"),
            "events_near",
        )


if __name__ == "__main__":
    unittest.main()
