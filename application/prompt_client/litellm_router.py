"""Shared LiteLLM wrapper for chat, embeddings, Module B, and GSoC/OIE.

PromptHandler stays DB-coupled (embedding contract + RAG). Everything else
that only needs a completion or embedding should call this module instead of
``import litellm`` so retry, rate-limit detection, and response parsing stay
in one place.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, List, Optional, Sequence

from application.prompt_client.llm_error_utils import is_rate_limit_error

logger = logging.getLogger(__name__)

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
        import litellm
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


# LiteLLM model id is usually ``provider/model-name``. Env var names follow
# LiteLLM's conventions so any supported chat provider can drive Module B.
_PROVIDER_API_KEY_ENV: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "vertex_ai": ("GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_API_KEY"),
    "azure": ("AZURE_API_KEY", "AZURE_OPENAI_API_KEY"),
    "groq": ("GROQ_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "cohere": ("COHERE_API_KEY",),
    "together_ai": ("TOGETHERAI_API_KEY", "TOGETHER_API_KEY"),
    "fireworks_ai": ("FIREWORKS_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
}

# Keys we treat as "some LLM is configured" for a soft preflight.
_ANY_LLM_KEY_ENV: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHERAI_API_KEY",
    "TOGETHER_API_KEY",
    "FIREWORKS_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
)


def provider_from_model(model: str) -> str:
    """Return LiteLLM provider prefix (``openai`` from ``openai/gpt-4o-mini``)."""
    s = (model or "").strip()
    if "/" in s:
        return s.split("/", 1)[0].strip().lower()
    return "openai"


def api_key_env_names_for_model(model: str) -> tuple[str, ...]:
    """Env var names LiteLLM typically needs for ``model``."""
    return _PROVIDER_API_KEY_ENV.get(provider_from_model(model), ("OPENAI_API_KEY",))


def has_credentials_for_model(model: str) -> bool:
    """True if any expected API-key env var for ``model`` is set and non-empty."""
    for name in api_key_env_names_for_model(model):
        if (os.environ.get(name) or "").strip():
            return True
    return False


def any_llm_api_key_present() -> bool:
    """True if any common chat-provider API key env var is set."""
    return any((os.environ.get(name) or "").strip() for name in _ANY_LLM_KEY_ENV)


def missing_credentials_hint(model: str) -> str:
    """Human-readable hint when credentials for ``model`` are missing."""
    needed = " or ".join(api_key_env_names_for_model(model))
    lines = [
        f"No API key found for model {model!r} (need {needed} in .env).",
        "Module B uses LiteLLM — set CRE_NOISE_FILTER_LLM_MODEL to a "
        "provider/model you have a key for, for example:",
        "  openai/gpt-4o-mini          + OPENAI_API_KEY",
        "  anthropic/claude-haiku-4-5  + ANTHROPIC_API_KEY",
        "  gemini/gemini-2.5-flash     + GEMINI_API_KEY",
        "  groq/llama-3.3-70b-versatile + GROQ_API_KEY",
        "Or pass --ingest_keep_all for an offline dump (not a real classification test).",
    ]
    if any_llm_api_key_present():
        lines.insert(
            1,
            "A different provider key is set — point CRE_NOISE_FILTER_LLM_MODEL "
            "(or --ingest_model) at a model for that provider.",
        )
    return "\n".join(lines)
