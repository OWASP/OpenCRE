"""Librarian C.2 prefers phase4 modern rerank when MODERN_RERANK is on."""

from __future__ import annotations

import unittest
from pathlib import Path


class LibrarianModernRerankWireTest(unittest.TestCase):
    def test_cross_encoder_calls_try_modern(self) -> None:
        src = Path("application/utils/librarian/cross_encoder.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_try_modern_rerank_order", src)
        self.assertIn("MODERN_RERANK", src)
        self.assertIn("rerank_and_compress", src)


if __name__ == "__main__":
    unittest.main()
