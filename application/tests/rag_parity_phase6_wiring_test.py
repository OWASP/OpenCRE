"""TASK-14.16: ask answer path wraps phase6 traced_span."""

from __future__ import annotations

import unittest
from pathlib import Path


class Phase6AskWiringTest(unittest.TestCase):
    def test_answer_uses_traced_span(self) -> None:
        src = Path("application/utils/comprehension/answer.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("traced_span", src)
        self.assertIn("phase6_observability", src)


if __name__ == "__main__":
    unittest.main()
