"""Module B Stage 2: LLM relevance classifier (recall-first).

Self-contained by design (decided 2026-06-18, Option B): this module talks to
LiteLLM directly rather than wrapping PromptHandler, whose constructor is
DB-coupled and whose retry/litellm members are private. We reuse the one
shared, public piece -- llm_error_utils.is_rate_limit_error -- inside a small
retry loop over the upstream CRE_LLM_MAX_RETRIES / CRE_LLM_RETRY_SLEEP_SECONDS
vars, so noise filtering and the chatbot share one retry policy.

The classifier uses a dedicated cheap model (config.llm_model, default
gemini/gemini-2.5-flash-lite) and never falls back to CRE_LLM_CHAT_MODEL:
Module B is the cheap gate and must stay decoupled from the chatbot's model.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterator

from pydantic import ValidationError

from application.prompt_client.llm_error_utils import is_rate_limit_error
from application.utils.noise_filter.config_loader import NoiseFilterConfig
from application.utils.noise_filter.prompts import (
    SYSTEM_PROMPT_WITH_EXAMPLES,
    build_user_prompt,
)
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult

logger = logging.getLogger(__name__)

_SCHEMA_NAME = "noise_filter_classification"

# Strict response schema (response_format). additionalProperties=False and all
# keys required is what providers expect in strict json_schema mode.
CLASSIFY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "label": {
                        "type": "string",
                        "enum": ["KNOWLEDGE", "NOISE", "UNCERTAIN"],
                    },
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": ["index", "label", "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

_TRUNCATION_NOTE = " …[truncated]"


def _uncertain(reason: str) -> ClassifyResult:
    """Build the fallback verdict used when the LLM output can't be trusted."""
    return ClassifyResult(label="UNCERTAIN", confidence=0.0, reasoning=reason)


def _batches(seq: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield consecutive slices of `seq` of length `size` (last may be shorter)."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _extract_text(resp: Any) -> str:
    """Pull message content from a LiteLLM response (object or dict shaped)."""
    try:
        choices = resp.choices if hasattr(resp, "choices") else resp["choices"]
        first = choices[0]
        msg = first.message if hasattr(first, "message") else first["message"]
        content = msg.content if hasattr(msg, "content") else msg["content"]
        return content or ""
    except (AttributeError, KeyError, IndexError, TypeError):
        return ""


class LLMClassifier:
    """Stage 2 classifier: ChangeRecord -> ClassifyResult via a cheap LLM."""

    def __init__(self, config: NoiseFilterConfig) -> None:
        self.config = config
        try:
            import litellm  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "litellm is required for the Module B Stage 2 classifier"
            ) from e
        self._litellm = litellm
        self._max_retries = int(os.environ.get("CRE_LLM_MAX_RETRIES", "2"))
        self._retry_sleep_seconds = int(
            os.environ.get("CRE_LLM_RETRY_SLEEP_SECONDS", "15")
        )

    def classify_batch(self, records: list[ChangeRecord]) -> list[ClassifyResult]:
        """Classify records, one verdict per record in input order.

        Splits into config.batch_size groups; each group is one LLM call.
        """
        verdicts: list[ClassifyResult] = []
        for batch in _batches(records, self.config.batch_size):
            verdicts.extend(self._classify_one_batch(batch))
        return verdicts

    # --- internals --------------------------------------------------------

    def _truncate(self, text: str) -> str:
        limit = self.config.max_chars
        if len(text) <= limit:
            return text
        return text[:limit] + _TRUNCATION_NOTE

    def _classify_one_batch(self, batch: list[ChangeRecord]) -> list[ClassifyResult]:
        items = [(rec.span.heading_path, self._truncate(rec.text)) for rec in batch]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_WITH_EXAMPLES},
            {"role": "user", "content": build_user_prompt(items)},
        ]
        try:
            text = self._call_llm(messages)
        except Exception as e:  # noqa: BLE001 -- a bad batch must not kill the run
            logger.warning(
                "LLM classification failed for batch of %s: %s; marking UNCERTAIN",
                len(batch),
                e,
            )
            return [_uncertain("llm_call_failed") for _ in batch]
        return self._parse(text, len(batch))

    def _call_llm(self, messages: list[dict]) -> str:
        strict_format = {
            "type": "json_schema",
            "json_schema": {
                "name": _SCHEMA_NAME,
                "strict": True,
                "schema": CLASSIFY_RESPONSE_SCHEMA,
            },
        }
        try:
            resp = self._completion_with_retry(
                messages=messages, response_format=strict_format
            )
        except Exception as e:  # noqa: BLE001 -- provider may not support strict schema
            logger.warning(
                "strict json_schema mode failed for model=%s: %s; retrying json_object",
                self.config.llm_model,
                e,
            )
            resp = self._completion_with_retry(
                messages=messages, response_format={"type": "json_object"}
            )
        return _extract_text(resp)

    def _completion_with_retry(self, **kwargs: Any) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                return self._litellm.completion(
                    model=self.config.llm_model, temperature=0.0, **kwargs
                )
            except Exception as e:
                if not is_rate_limit_error(e) or attempt >= self._max_retries:
                    raise
                logger.info(
                    "rate/quota limited; sleeping %ss (attempt %s/%s)",
                    self._retry_sleep_seconds,
                    attempt + 1,
                    self._max_retries + 1,
                )
                time.sleep(self._retry_sleep_seconds)
        raise RuntimeError("unreachable: retry loop exited unexpectedly")

    def _parse(self, text: str, n: int) -> list[ClassifyResult]:
        verdicts = [_uncertain("malformed_output") for _ in range(n)]
        try:
            data = json.loads(text)
            results = data.get("results", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, TypeError):
            logger.warning("could not parse LLM JSON output; marking batch UNCERTAIN")
            return verdicts
        for item in results:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or not (0 <= idx < n):
                continue
            try:
                verdicts[idx] = ClassifyResult.model_validate(
                    {
                        "label": item.get("label"),
                        "confidence": item.get("confidence"),
                        "reasoning": item.get("reasoning"),
                    }
                )
            except ValidationError:
                # leave this slot as the UNCERTAIN/malformed default
                continue
        return verdicts


__all__ = [
    "CLASSIFY_RESPONSE_SCHEMA",
    "LLMClassifier",
]
