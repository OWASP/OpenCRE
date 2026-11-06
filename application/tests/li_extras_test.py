"""TASK-17.6/17.8: LI_HYDE / LI_REWRITE / LI_RERANK are gated and fail open."""

from __future__ import annotations

import unittest
from unittest import mock

from application.utils.comprehension import flags, li_extras
from application.utils.owasp_agent.lane_similarity import LaneHit


def _hits(n: int = 5) -> list:
    return [
        LaneHit(channel="c", score=1.0 - i / 10, url=f"u{i}", content=f"text {i}")
        for i in range(n)
    ]


class LiExtrasTest(unittest.TestCase):
    def test_flags_declared_and_default_off(self) -> None:
        for name in ("LI_HYDE", "LI_REWRITE", "LI_RERANK"):
            self.assertIn(name, flags.NAMES)
            self.assertNotIn(name, flags.DEFAULT_ON)

    def test_rerank_off_returns_input_unchanged(self) -> None:
        from application.utils.comprehension.retrieve import _li_rerank

        hits = _hits()
        self.assertIs(_li_rerank("q", hits), hits)

    def test_rerank_fails_open(self) -> None:
        hits = _hits()
        with mock.patch.object(li_extras, "_adapter", side_effect=RuntimeError):
            out = li_extras.rerank_hits("q", hits)
        self.assertEqual([h.url for h in out], [h.url for h in hits])

    def test_rerank_short_list_untouched(self) -> None:
        hits = _hits(2)
        self.assertEqual(li_extras.rerank_hits("q", hits), hits)

    def test_hyde_and_rewrite_fail_open(self) -> None:
        with mock.patch.object(
            li_extras, "_adapter", side_effect=RuntimeError
        ), mock.patch.object(li_extras, "_complete_text", side_effect=RuntimeError):
            self.assertEqual(li_extras.hyde_queries("q"), [])
            self.assertEqual(li_extras.rewrite_queries("q"), [])

    def test_rewrite_returns_new_query(self) -> None:
        with mock.patch.object(
            li_extras, "_complete_text", return_value='"owasp samm maturity"'
        ):
            self.assertEqual(
                li_extras.rewrite_queries("what is samm?"), ["owasp samm maturity"]
            )


if __name__ == "__main__":
    unittest.main()
