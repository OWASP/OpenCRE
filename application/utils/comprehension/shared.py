"""One PromptHandler per process: constructing it re-checks the embedding contract (~1.5s each)."""

from __future__ import annotations

import os
import threading
from typing import Any

_LOCK = threading.Lock()
_HANDLER: Any = None


def shared_handler(database: Any) -> Any:
    """A lazily created, cached PromptHandler(load_all_embeddings=False)."""
    from application.prompt_client import prompt_client

    global _HANDLER
    if (os.environ.get("OWASP_SHARED_HANDLER", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return prompt_client.PromptHandler(database, load_all_embeddings=False)
    with _LOCK:
        if _HANDLER is None:
            _HANDLER = prompt_client.PromptHandler(database, load_all_embeddings=False)
        return _HANDLER


def warm_up() -> bool:
    """Pay the one-off costs (imports, handler, embedding client, DB connection) before real traffic.

    The first question after a restart took ~30 s; this runs once in the background at server
    start. Never raises. Off with OWASP_WARMUP=0.
    """
    if (os.environ.get("OWASP_WARMUP", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    try:
        from application.database import db as db_mod
        from application.utils.comprehension.embedcache import cached
        from application.utils.comprehension.retrieve import fetch_comprehension_hits

        handler = shared_handler(db_mod.Node_collection())
        cached(handler.get_text_embeddings)("warm up")
        fetch_comprehension_hits("warm up")
        from application.utils.owasp_agent.candidate_picker import default_completion_fn

        complete = default_completion_fn()
        if complete is not None:
            complete([{"role": "user", "content": "Reply with OK."}])
        return True
    except Exception:  # noqa: BLE001 - warm-up must never stop the server
        return False
