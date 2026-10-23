import os
import unittest
from unittest import mock

from application.utils import rate_limit, roles


class RateLimitTest(unittest.TestCase):
    def setUp(self):
        rate_limit.reset_memory()
        self._env = mock.patch.dict(
            os.environ,
            {
                "RATE_LIMIT_ENABLED": "1",
                "RATE_LIMIT_PER_MINUTE": "3",
                "RATE_LIMIT_PER_HOUR": "5",
                "RATE_LIMIT_PER_DAY": "9",
                "RATE_LIMIT_ADMIN_MULTIPLIER": "2",
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_minute_limit_then_blocked_with_retry_after(self):
        for _ in range(3):
            rate_limit.check_and_count("a@owasp.org", roles.USER)
        with self.assertRaises(rate_limit.RateLimited) as cm:
            rate_limit.check_and_count("a@owasp.org", roles.USER)
        self.assertEqual(cm.exception.window, "minute")
        self.assertTrue(1 <= cm.exception.retry_after <= 60)
        self.assertIn("3 questions per minute", cm.exception.message())

    def test_limits_are_per_account_and_case_insensitive(self):
        for _ in range(3):
            rate_limit.check_and_count("A@owasp.org", roles.USER)
        rate_limit.check_and_count(
            "b@owasp.org", roles.USER
        )  # a different account is unaffected
        with self.assertRaises(rate_limit.RateLimited):
            rate_limit.check_and_count("a@OWASP.org", roles.USER)

    def test_admins_get_a_multiple(self):
        for _ in range(6):
            rate_limit.check_and_count("boss@owasp.org", roles.ADMIN)
        with self.assertRaises(rate_limit.RateLimited):
            rate_limit.check_and_count("boss@owasp.org", roles.ADMIN)

    def test_disabled_and_anonymous_are_not_limited(self):
        with mock.patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "0"}):
            for _ in range(50):
                rate_limit.check_and_count("a@owasp.org", roles.USER)
        for _ in range(50):
            rate_limit.check_and_count("", roles.USER)

    def test_exempt_accounts_are_not_limited(self):
        with mock.patch.dict(
            os.environ, {"RATE_LIMIT_EXEMPT_EMAILS": "Bot@owasp.org, other@x.org"}
        ):
            for _ in range(50):
                rate_limit.check_and_count("bot@owasp.org", roles.USER)
            for _ in range(3):
                rate_limit.check_and_count("jane@owasp.org", roles.USER)
            with self.assertRaises(rate_limit.RateLimited):
                rate_limit.check_and_count("jane@owasp.org", roles.USER)

    def test_hour_window_counts_across_minutes(self):
        now = [10_000.0]
        with mock.patch("time.time", side_effect=lambda: now[0]):
            for i in range(5):
                now[0] = 10_000.0 + i * 100  # a new minute each time, same hour
                rate_limit.check_and_count("c@owasp.org", roles.USER)
            now[0] = 10_000.0 + 5 * 100
            with self.assertRaises(rate_limit.RateLimited) as cm:
                rate_limit.check_and_count("c@owasp.org", roles.USER)
        self.assertEqual(cm.exception.window, "hour")
