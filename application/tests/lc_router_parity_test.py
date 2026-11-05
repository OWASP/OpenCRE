"""TASK-14.4: hermetic LC vs regex parity on known intents / misroute cases."""

from __future__ import annotations

import os
import unittest
from unittest import mock

# Gold cases: (question, expected_regex_intent). LC should match when mock returns same.
_PARITY_CASES = (
    ("How do I prevent SSRF?", "cre_normative"),
    ("How do I prevent XSS?", "cre_normative"),
    ("Are there OWASP events near London?", "events_near"),
    ("What is the OWASP London chapter?", "chapter_lookup"),
    ("Who is the chapter leader?", "clarify"),
    ("When is the next meetup?", "clarify"),
    ("List OWASP board members for this year", "board_members"),
    ("How many OWASP projects are there?", "count_projects"),
)


class LcRouterParityTest(unittest.TestCase):
    def test_regex_gold_intents_stable(self) -> None:
        from application.utils.owasp_agent.router import _classify_intent_regex

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "0"}):
            for q, expected in _PARITY_CASES:
                got = _classify_intent_regex(q)
                self.assertEqual(got, expected, q)

    def test_lc_parity_when_lc_agrees(self) -> None:
        """When LC returns the regex gold intent, classify_intent matches."""
        from application.utils.owasp_agent.router import (
            _classify_intent_regex,
            classify_intent,
        )

        for q, expected in _PARITY_CASES:
            regex_intent = _classify_intent_regex(q)
            with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
                with mock.patch(
                    "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                    return_value=regex_intent,
                ):
                    self.assertEqual(classify_intent(q), expected, q)

    def test_lc_misroute_notes_normative_not_clarify(self) -> None:
        """Documented misroute: LC clarify on normative must be measurable in tests."""
        from application.utils.owasp_agent.router import classify_intent

        # With one-call routing, whatever LC returns is SoT — this records the risk.
        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="clarify",
            ):
                intent = classify_intent("How do I prevent SSRF?")
        self.assertEqual(intent, "clarify")  # intentional: ship gate catches this


if __name__ == "__main__":
    unittest.main()
