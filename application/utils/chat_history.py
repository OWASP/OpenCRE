"""Normalize chat history for /rest/v1/completion (native LiteLLM messages)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Cap prior turns sent to the model / agent (excludes the current prompt turn).
MAX_HISTORY_MESSAGES = 20


def normalize_chat_messages(
    raw: Any, *, max_messages: int = MAX_HISTORY_MESSAGES
) -> List[Dict[str, str]]:
    """Return ``[{role, content}, ...]`` with only user/assistant string turns."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = item.get("content")
        if content is None:
            content = item.get("message")
        text = str(content or "").strip()
        if not text:
            continue
        out.append({"role": role, "content": text})
    if max_messages > 0 and len(out) > max_messages:
        out = out[-max_messages:]
    return out


def split_prompt_and_history(
    body: Dict[str, Any],
) -> Tuple[str, List[Dict[str, str]]]:
    """Extract current user prompt + prior history from a completion request body.

    Accepts ``prompt`` and optional ``messages``. If ``messages`` ends with the
    current user turn, that turn is treated as the prompt and removed from history.
    """
    messages = normalize_chat_messages(body.get("messages"))
    prompt = str(body.get("prompt") or "").strip()
    if not prompt and messages and messages[-1]["role"] == "user":
        prompt = messages[-1]["content"]
        messages = messages[:-1]
    elif (
        prompt
        and messages
        and messages[-1]["role"] == "user"
        and messages[-1]["content"] == prompt
    ):
        messages = messages[:-1]
    return prompt, messages
