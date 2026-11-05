"""TASK-14.24: LC_ROUTER on → one LC call first; regex only on LLM/API failure."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class LcRouterOneCallTest(unittest.TestCase):
    def test_lc_first_when_flag_on(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value="project_lookup",
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                ) as regex:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "project_lookup")
        lc.assert_called_once()
        regex.assert_not_called()

    def test_regex_only_when_lc_returns_none(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                return_value=None,
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                    return_value="cre_normative",
                ) as regex:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "cre_normative")
        lc.assert_called_once()
        regex.assert_called_once()

    def test_regex_only_when_lc_raises(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "1"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
                side_effect=RuntimeError("api down"),
            ):
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                    return_value="cre_normative",
                ) as regex:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "cre_normative")
        regex.assert_called_once()

    def test_flag_off_uses_regex_only(self) -> None:
        from application.utils.owasp_agent.router import classify_intent

        with mock.patch.dict(os.environ, {"OWASP_CX_LC_ROUTER": "0"}):
            with mock.patch(
                "application.utils.owasp_agent.lc_router.classify_intent_langchain",
            ) as lc:
                with mock.patch(
                    "application.utils.owasp_agent.router._classify_intent_regex",
                    return_value="cre_normative",
                ) as regex:
                    intent = classify_intent(
                        "How do I stop SQL injection in my application?"
                    )
        self.assertEqual(intent, "cre_normative")
        regex.assert_called_once()
        lc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
