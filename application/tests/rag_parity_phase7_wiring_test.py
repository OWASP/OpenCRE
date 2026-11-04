"""TASK-14.17: ask CACHE path can use phase7 Redis answer cache."""

from __future__ import annotations

import unittest
from pathlib import Path


class Phase7AskWiringTest(unittest.TestCase):
    def test_answer_wires_redis_answer_cache(self) -> None:
        src = Path("application/utils/comprehension/answer.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("build_answer_cache", src)
        self.assertIn("CRE_RAG_PARITY_REDIS_ANSWER_CACHE", src)
        self.assertIn("put_cached_answer", src)


if __name__ == "__main__":
    unittest.main()
