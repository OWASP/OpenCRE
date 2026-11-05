"""TASK-14.24: when LC_ROUTER on, LC is primary; soft-gate (regex-first) is gone."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class LcRouterSoftGateTest(unittest.TestCase):
    def test_normative_ask_uses_lc_when_flag_on(self) -> None:
        """LC result wins even when it would have been a soft intent under old gate."""
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="cre_normative",
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                ) as regex:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "cre_normative")
        lc.assert_called_once()
        regex.assert_not_called()

    def test_lc_intent_used_without_regex_clarify_gate(self) -> None:
        """LC runs on every ask when flag on — not only when regex yields clarify."""
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="count_projects",
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                    return_value="cre_normative",
                ) as regex:
                    intent = classify_intent("who is the chapter leader?")
        self.assertEqual(intent, "count_projects")
        lc.assert_called_once()
        regex.assert_not_called()

    def test_lc_clarify_accepted_when_lc_returns_it(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="clarify",
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                ) as regex:
                    intent = classify_intent("who is the chapter leader?")
        self.assertEqual(intent, "clarify")
        lc.assert_called_once()
        regex.assert_not_called()


if __name__ == "__main__":
    unittest.main()
