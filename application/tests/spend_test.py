"""Per-account daily LLM budget: counting, refusing, and the MCP/chat entry points."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from application.prompt_client import litellm_router
from application.utils import rate_limit, spend

ENV = {
    "BUDGET_ENABLED": "1",
    "BUDGET_DAILY_USD": "1.00",
    "RATE_LIMIT_ADMIN_MULTIPLIER": "4",
    "RATE_LIMIT_EXEMPT_EMAILS": "",
    "LOGIN_ALLOWED_DOMAINS": "owasp.org",
    "ADMIN_EMAILS": "boss@owasp.org",
}


def fake_cost(value: float) -> Any:
    return patch("litellm.completion_cost", return_value=value)


class SpendTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(os.environ, ENV)
        self._env.start()
        spend.reset_memory()
        rate_limit.reset_memory()
        # Force the in-process counters so the test never needs Redis.
        self._redis = patch.object(spend, "_redis", return_value=None)
        self._redis.start()

    def tearDown(self) -> None:
        self._redis.stop()
        self._env.stop()
        spend.clear()

    def test_calls_are_charged_to_the_current_account(self) -> None:
        with spend.charging("Alice@owasp.org"), fake_cost(0.25):
            spend.record(object(), "m")
            spend.record(object(), "m")
        self.assertAlmostEqual(spend.spent_usd("alice@owasp.org"), 0.5)

    def test_calls_outside_an_account_cost_nobody(self) -> None:
        with fake_cost(0.25):
            spend.record(object(), "m")
        self.assertEqual(spend.spent_usd("alice@owasp.org"), 0.0)

    def test_account_over_budget_is_refused_until_the_day_resets(self) -> None:
        with spend.charging("alice@owasp.org"), fake_cost(1.0):
            spend.record(object(), "m")
        with self.assertRaises(spend.BudgetExceeded) as ctx:
            spend.check_budget("alice@owasp.org", "user")
        self.assertIn("$1.00", ctx.exception.message())
        self.assertGreater(ctx.exception.retry_after, 0)
        spend.check_budget("bob@owasp.org", "user")  # another account is unaffected

    def test_under_budget_is_allowed(self) -> None:
        with spend.charging("alice@owasp.org"), fake_cost(0.99):
            spend.record(object(), "m")
        spend.check_budget("alice@owasp.org", "user")

    def test_admins_get_a_multiple_of_the_budget(self) -> None:
        with spend.charging("boss@owasp.org"), fake_cost(3.5):
            spend.record(object(), "m")
        spend.check_budget("boss@owasp.org", "admin")  # 3.50 < 4.00
        with self.assertRaises(spend.BudgetExceeded):
            spend.check_budget("boss@owasp.org", "user")

    def test_exempt_and_disabled_accounts_are_never_refused(self) -> None:
        with spend.charging("eval@owasp.org"), fake_cost(50.0):
            spend.record(object(), "m")
        with patch.dict(os.environ, {"RATE_LIMIT_EXEMPT_EMAILS": "eval@owasp.org"}):
            spend.check_budget("eval@owasp.org", "user")
        with patch.dict(os.environ, {"BUDGET_ENABLED": "0"}):
            spend.check_budget("eval@owasp.org", "user")

    def test_unknown_model_pricing_never_raises(self) -> None:
        with spend.charging("alice@owasp.org"), patch(
            "litellm.completion_cost", side_effect=Exception("no price")
        ):
            spend.record(object(), "mystery")
        self.assertEqual(spend.spent_usd("alice@owasp.org"), 0.0)

    def test_router_completion_and_embedding_report_their_cost(self) -> None:
        client = MagicMock()
        with spend.charging("alice@owasp.org"), fake_cost(0.1):
            litellm_router.completion(
                model="m", messages=[{"role": "user", "content": "hi"}], client=client
            )
            litellm_router.embedding(model="e", input="hi", client=client)
        self.assertAlmostEqual(spend.spent_usd("alice@owasp.org"), 0.2)

    def test_resilient_completion_reports_its_cost(self) -> None:
        client = MagicMock()
        with spend.charging("alice@owasp.org"), fake_cost(0.3):
            litellm_router.resilient_completion(
                model="m", messages=[{"role": "user", "content": "hi"}], client=client
            )
        self.assertAlmostEqual(spend.spent_usd("alice@owasp.org"), 0.3)

    def test_run_charged_sets_and_restores_the_account(self) -> None:
        seen = spend.run_charged("a@owasp.org", spend.current_account)
        self.assertEqual(seen, "a@owasp.org")
        self.assertIsNone(spend.current_account())


if __name__ == "__main__":
    unittest.main()
