"""Phase 7: LangGraph checkpointer factory (Redis/Postgres) — not ConversationBuffer."""

from __future__ import annotations

import logging
from typing import Any, Optional

from application.utils.rag_parity.flags import RagParityFlags, load_flags

logger = logging.getLogger(__name__)


class MemoryCheckpointer:
    """Hermetic stand-in when LangGraph Redis/Postgres checkpointer is unavailable."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def put(self, thread_id: str, state: Any) -> None:
        self._store[thread_id] = state

    def get(self, thread_id: str) -> Any:
        return self._store.get(thread_id)


def build_checkpointer(
    flags: Optional[RagParityFlags] = None,
    *,
    backend: str = "memory",
    conn: Any = None,
) -> Any:
    """Return a checkpointer. Never uses ConversationBuffer as session memory."""
    cfg = flags or load_flags()
    if not cfg.langgraph_checkpointer:
        return MemoryCheckpointer()
    kind = (backend or "memory").strip().lower()
    if kind == "redis" and conn is not None:
        try:
            from langgraph.checkpoint.redis import RedisSaver  # type: ignore

            return RedisSaver(conn)
        except Exception:  # noqa: BLE001
            logger.debug("RedisSaver unavailable; memory fallback", exc_info=True)
    if kind in ("postgres", "postgresql") and conn is not None:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore

            return PostgresSaver(conn)
        except Exception:  # noqa: BLE001
            logger.debug("PostgresSaver unavailable; memory fallback", exc_info=True)
    return MemoryCheckpointer()
