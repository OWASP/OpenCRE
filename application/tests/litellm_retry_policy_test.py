import os
import unittest
from unittest.mock import patch

from application.prompt_client import litellm_router

RETRIES = "CRE_LLM_MAX_RETRIES"
SLEEP = "CRE_LLM_RETRY_SLEEP_SECONDS"


class TestRetryPolicy(unittest.TestCase):
    def _policy(self, **env):
        with patch.dict(os.environ, env, clear=False):
            for k in (RETRIES, SLEEP):
                if k not in env:
                    os.environ.pop(k, None)
            return litellm_router.retry_policy()

    def test_defaults_when_unset(self):
        with self.assertNoLogs(litellm_router.logger, level="WARNING"):
            self.assertEqual(self._policy(), (2, 15))

    def test_valid_values(self):
        self.assertEqual(self._policy(**{RETRIES: "5", SLEEP: "3"}), (5, 3))

    def test_whitespace_is_tolerated(self):
        self.assertEqual(self._policy(**{RETRIES: " 4 ", SLEEP: " 1 "}), (4, 1))

    def test_illegal_values_fall_back_and_warn(self):
        for bad in ("abc", "1.5", "2s", "0x10"):
            with self.subTest(bad=bad):
                with self.assertLogs(litellm_router.logger, level="WARNING") as cm:
                    result = self._policy(**{RETRIES: bad, SLEEP: bad})
                self.assertEqual(result, (2, 15))
                self.assertEqual(len(cm.records), 2)

    def test_empty_values_fall_back_and_warn(self):
        with self.assertLogs(litellm_router.logger, level="WARNING"):
            self.assertEqual(self._policy(**{RETRIES: "", SLEEP: "  "}), (2, 15))

    def test_negative_values_clamp_to_zero(self):
        with self.assertLogs(litellm_router.logger, level="WARNING"):
            self.assertEqual(self._policy(**{RETRIES: "-3", SLEEP: "-1"}), (0, 0))

    def test_zero_is_preserved(self):
        self.assertEqual(self._policy(**{RETRIES: "0", SLEEP: "0"}), (0, 0))

    def test_only_one_bad_value_does_not_affect_other(self):
        with self.assertLogs(litellm_router.logger, level="WARNING"):
            self.assertEqual(self._policy(**{RETRIES: "nope", SLEEP: "7"}), (2, 7))

    def test_with_rate_limit_retry_survives_bad_env(self):
        with patch.dict(os.environ, {RETRIES: "junk", SLEEP: "junk"}):
            self.assertEqual(
                litellm_router.with_rate_limit_retry(lambda: "ok", context="t"), "ok"
            )


if __name__ == "__main__":
    unittest.main()
