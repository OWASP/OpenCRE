"""Phase 7: answer cache, queue lock policy, budgets, checkpointer."""

import unittest

from application.utils.rag_parity.flags import RagParityFlags
from application.utils.rag_parity.phase4_rerank import RerankHit
from application.utils.rag_parity.phase7_answer_cache import (
    InProcessAnswerCache,
    get_cached_answer,
    put_cached_answer,
)
from application.utils.rag_parity.phase7_budgets import (
    apply_context_budget,
    select_budget,
)
from application.utils.rag_parity.phase7_checkpointer import (
    MemoryCheckpointer,
    build_checkpointer,
)
from application.utils.rag_parity.phase7_queue_lock import (
    QueueLockError,
    resolve_queue_lock_policy,
)


class AnswerCacheTest(unittest.TestCase):
    def test_roundtrip(self) -> None:
        cache = InProcessAnswerCache()
        put_cached_answer(
            cache, "hello", {"answer": "world"}, model="m", ttl_seconds=60
        )
        self.assertEqual(
            get_cached_answer(cache, "hello", model="m")["answer"], "world"
        )


class QueueLockTest(unittest.TestCase):
    def test_postgres_locks_when_default_on(self) -> None:
        p = resolve_queue_lock_policy(
            dialect="postgresql",
            flags=RagParityFlags(queue_row_lock_default=True),
        )
        self.assertTrue(p.lock_rows)

    def test_sqlite_refuses_silent_degrade(self) -> None:
        with self.assertRaises(QueueLockError):
            resolve_queue_lock_policy(
                dialect="sqlite",
                flags=RagParityFlags(queue_row_lock_default=True),
            )


class BudgetTest(unittest.TestCase):
    def test_asvs_budget_caps_docs_and_chars(self) -> None:
        budget = select_budget("asvs")
        hits = [RerankHit(str(i), "X" * 2000, float(i)) for i in range(20)]
        out = apply_context_budget(hits, budget)
        self.assertLessEqual(len(out), budget.max_docs)
        self.assertLessEqual(sum(len(h.text) for h in out), budget.max_chars)


class CheckpointerTest(unittest.TestCase):
    def test_memory_when_flag_off(self) -> None:
        cp = build_checkpointer(RagParityFlags(langgraph_checkpointer=False))
        self.assertIsInstance(cp, MemoryCheckpointer)
        cp.put("t1", {"x": 1})
        self.assertEqual(cp.get("t1"), {"x": 1})


if __name__ == "__main__":
    unittest.main()
