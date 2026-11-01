"""Opt-in push of OWASP agent meta into the shared ``embeddings`` table.

Kept out of ``sync.py`` on purpose: ``sync_all`` only fills the agent index and
must never import the CRE database layer. Callers (CLI, admin panel, scheduler)
invoke :func:`embed_meta_if_enabled` after ``sync_all``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Sequence

from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.meta_embeddings import sync_meta_embeddings
from application.utils.owasp_agent.sync import SyncReport

EmbedFn = Callable[[str], Sequence[float]]

_FLAG = "OWASP_AGENT_EMBED_META"


def embed_meta_enabled() -> bool:
    return os.environ.get(_FLAG, "").strip() in ("1", "true", "yes")


def embed_meta_if_enabled(
    store: IndexStore,
    report: SyncReport,
    *,
    database: Optional[Any] = None,
    embed_fn: Optional[EmbedFn] = None,
) -> bool:
    """Embed meta (+ evidence notes) for lane routing when ``OWASP_AGENT_EMBED_META`` is on.

    Returns True when the push completed. Failures are logged to the store's
    sync log and appended to ``report.errors``; nothing is raised. ``database``
    and ``embed_fn`` are built lazily (``Node_collection`` / ``PromptHandler``)
    only when not injected.
    """
    if not embed_meta_enabled():
        return False
    try:
        if database is None:
            from application.database import db as db_mod

            database = db_mod.Node_collection()
        if embed_fn is None:
            from application.prompt_client import prompt_client

            handler = prompt_client.PromptHandler(database, load_all_embeddings=False)

            def embed_fn(text: str) -> List[float]:
                return handler.get_text_embeddings(text)

        stats = sync_meta_embeddings(store, database, embed_fn)
        store.log_sync("meta_embeddings", "ok", str(stats))
        return True
    except Exception as exc:  # noqa: BLE001
        store.log_sync("meta_embeddings", "error", str(exc))
        report.errors.append(f"meta_embeddings: {exc}")
        return False
