"""Shared LiteLLM wrapper for chat, embeddings, Module B, and GSoC/OIE.

PromptHandler stays DB-coupled (embedding contract + RAG). Everything else
that only needs a completion or embedding should call this module instead of
``import litellm`` so retry, rate-limit detection, and response parsing stay
in one place.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import time
from typing import Any, Callable, List, Optional, Sequence

from application.prompt_client.llm_error_utils import is_rate_limit_error

LlmFn = Callable[[str, str], str]


def retry_policy() -> tuple[int, int]:
    """Return (max_retries, sleep_seconds) from CRE_LLM_* env vars."""
    return (
        int(os.environ.get("CRE_LLM_MAX_RETRIES", "2")),
        int(os.environ.get("CRE_LLM_RETRY_SLEEP_SECONDS", "15")),
    )


def get_litellm() -> Any:
    """Import LiteLLM or raise the same RuntimeError PromptHandler uses."""
    try:
        import litellm  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "litellm package is required for PromptHandler LLM calls"
        ) from exc
    return litellm


def with_rate_limit_retry(
    fn: Callable[[], Any],
    *,
    context: str,
    max_retries: Optional[int] = None,
    retry_sleep_seconds: Optional[int] = None,
) -> Any:
    default_retries, default_sleep = retry_policy()
    retries = default_retries if max_retries is None else max_retries
    sleep_s = default_sleep if retry_sleep_seconds is None else retry_sleep_seconds
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as err:
            if not is_rate_limit_error(err) or attempt >= retries:
                raise
            logger.info(
                "rate/quota limited during %s; sleeping %ss (attempt %s/%s)",
                context,
                sleep_s,
                attempt + 1,
                retries + 1,
            )
            time.sleep(sleep_s)
    raise RuntimeError("unreachable: retry loop exited unexpectedly")


def extract_content_text(response: Any, *, strict: bool = True) -> str:
    """Pull assistant text from a LiteLLM completion (object or dict)."""
    choices = getattr(response, "choices", None)
    if not choices and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        if strict:
            raise ValueError("LLM response did not contain choices")
        return ""
    first = choices[0]
    msg = getattr(first, "message", None)
    if msg is None and isinstance(first, dict):
        msg = first.get("message")
    if msg is None:
        if strict:
            raise ValueError("LLM response did not contain message content")
        return ""
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    if content is None:
        if strict:
            raise ValueError("LLM response did not contain message content")
        return ""
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        ).strip()
    return str(content).strip()


def extract_embeddings(response: Any) -> List[List[float]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    if not isinstance(data, list):
        raise ValueError("Embedding response missing data list")
    vectors: List[List[float]] = []
    for item in data:
        emb = getattr(item, "embedding", None)
        if emb is None and isinstance(item, dict):
            emb = item.get("embedding")
        if not isinstance(emb, list):
            raise ValueError("Embedding item missing vector")
        vectors.append([float(x) for x in emb])
    return vectors


def completion(
    *,
    model: str,
    messages: Sequence[dict[str, Any]],
    context: str = "LiteLLM completion",
    client: Any = None,
    max_retries: Optional[int] = None,
    retry_sleep_seconds: Optional[int] = None,
    **kwargs: Any,
) -> Any:
    """LiteLLM chat completion with shared rate-limit retry."""
    llm = client if client is not None else get_litellm()

    def _call() -> Any:
        return llm.completion(model=model, messages=list(messages), **kwargs)

    return with_rate_limit_retry(
        _call,
        context=context,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )


def embedding(
    *,
    model: str,
    input: str | List[str],
    context: str = "LiteLLM embeddings",
    client: Any = None,
    max_retries: Optional[int] = None,
    retry_sleep_seconds: Optional[int] = None,
    **kwargs: Any,
) -> Any:
    llm = client if client is not None else get_litellm()

    def _call() -> Any:
        return llm.embedding(model=model, input=input, **kwargs)

    return with_rate_limit_retry(
        _call,
        context=context,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )


def completion_text(
    *,
    model: str,
    messages: Sequence[dict[str, Any]],
    strict: bool = True,
    **kwargs: Any,
) -> str:
    return extract_content_text(
        completion(model=model, messages=messages, **kwargs),
        strict=strict,
    )


def system_user_fn(
    model: str,
    *,
    temperature: float = 0.0,
    extra_try_kwargs: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> LlmFn:
    """Build ``(system, user) -> text`` for Librarian / OIE call sites."""

    def _call(system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if extra_try_kwargs:
            try:
                return completion_text(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    **extra_try_kwargs,
                    **kwargs,
                )
            except Exception:
                logger.debug(
                    "LiteLLM extra kwargs failed for model=%s; retrying without them",
                    model,
                    exc_info=True,
                )
        return completion_text(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )

    return _call
