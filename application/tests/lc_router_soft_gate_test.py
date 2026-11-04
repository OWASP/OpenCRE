"""TASK-14.4: soft LC intents must not override regex content routes."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class LcRouterSoftGateTest(unittest.TestCase):
    def test_normative_ask_not_stuck_on_lc_clarify(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="clarify",
            ):
                intent = classify_intent(
                    "How do I stop SQL injection in my application?"
                )
        # Regex path should win over soft LC clarify for normative how-to.
        self.assertNotEqual(intent, "clarify")
        self.assertIsInstance(intent, str)

    def test_hard_lc_intent_rescues_regex_clarify(self) -> None:
        """LC runs only when regex yields clarify; hard LC intent then wins."""
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.router._classify_intent_regex",
                return_value="clarify",
            ):
                with mock.patch(
                    "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                    return_value="count_projects",
                ) as lc:
                    intent = classify_intent("who is the chapter leader?")
        self.assertEqual(intent, "count_projects")
        lc.assert_called()

    def test_skips_lc_when_regex_confident(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.router._classify_intent_regex",
                return_value="cre_normative",
            ):
                with mock.patch(
                    "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                ) as lc:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "cre_normative")
        lc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
