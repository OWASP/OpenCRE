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
