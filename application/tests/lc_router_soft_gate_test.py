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

    def test_hard_lc_intent_still_used(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="count_projects",
            ):
                intent = classify_intent("how many OWASP projects are there?")
        self.assertEqual(intent, "count_projects")


if __name__ == "__main__":
    unittest.main()
