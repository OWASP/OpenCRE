"""Phase 6: observability gates + eval bridges (no paid path)."""

import os
import unittest
from unittest import mock

from application.utils.rag_parity.flags import RagParityFlags
from application.utils.rag_parity.phase6_eval import (
    GoldCase,
    neighbourhood_hit_at_k,
    run_deepeval_bridge,
    run_ragas_bridge,
)
from application.utils.rag_parity.phase6_observability import langfuse_enabled


class LangfuseGateTest(unittest.TestCase):
    def test_off_without_flag_or_keys(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            self.assertFalse(langfuse_enabled(RagParityFlags(langfuse=False)))
            self.assertFalse(langfuse_enabled(RagParityFlags(langfuse=True)))


class EvalBridgeTest(unittest.TestCase):
    def test_neighbourhood_hit(self) -> None:
        cases = [
            GoldCase("password", ["111"]),
            GoldCase("session", ["222"]),
        ]

        def retrieve(q: str):
            return ["111"] if "password" in q else ["999"]

        self.assertEqual(neighbourhood_hit_at_k(cases, retrieve, k=5), 0.5)
        r = run_ragas_bridge(cases, retrieve)
        self.assertEqual(r.hit_at_k, 0.5)
        d = run_deepeval_bridge(cases, retrieve)
        self.assertEqual(d.n, 2)


if __name__ == "__main__":
    unittest.main()
