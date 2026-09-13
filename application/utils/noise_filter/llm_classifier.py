"""Module B Stage 2: LLM relevance classifier (recall-first).

Self-contained by design (decided 2026-06-18, Option B): this module does not
construct PromptHandler (DB-coupled). Completions go through
``application.prompt_client.litellm_router`` so retry policy and parsing match
chat/embeddings. The classifier uses a dedicated cheap model
(config.llm_model, default gemini/gemini-2.5-flash-lite) and never falls back
to CRE_LLM_CHAT_MODEL: Module B is the cheap gate and must stay decoupled
from the chatbot's model.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from pydantic import ValidationError

from application.prompt_client.litellm_router import (
    completion as litellm_completion,
    extract_content_text,
    get_litellm,
    retry_policy,
)
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


# Reasons the fallback path marks a chunk UNCERTAIN -- B's own signals, not the
# model's verdict. LLM_CALL_FAILED is an *infrastructure* failure (the call raised
# after retries: rate limit, network, auth); the pipeline leaves those input rows
# `pending` for a later retry rather than finalizing them. MALFORMED_OUTPUT means
# the model responded but the output couldn't be parsed -- retrying tends to
# reproduce it, so it is persisted as UNCERTAIN, not retried.
LLM_CALL_FAILED = "llm_call_failed"
MALFORMED_OUTPUT = "malformed_output"


def _uncertain(reason: str) -> ClassifyResult:
    """Build the fallback verdict used when the LLM output can't be trusted."""
    return ClassifyResult(label="UNCERTAIN", confidence=0.0, reasoning=reason)


def _infra_failure() -> ClassifyResult:
    """Fallback for an LLM-call (infrastructure) failure. `retryable=True` is set
    here and *only* here -- the parser never sets it -- so the pipeline can trust
    it to leave the chunk's input row `pending` for a retry.
    """
    return ClassifyResult(
        label="UNCERTAIN", confidence=0.0, reasoning=LLM_CALL_FAILED, retryable=True
    )


def is_infra_failure(result: ClassifyResult) -> bool:
    """True if `result` came from B's LLM-call-failure path -- read from the
    *trusted* `retryable` flag, not the model-controlled `reasoning` string, so a
    model response that happens to say "llm_call_failed" can never be mistaken for
    an infrastructure failure. The pipeline uses this to leave such chunks' input
    rows `pending` for a later retry.
    """
    return result.retryable


def _batches(seq: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield consecutive slices of `seq` of length `size` (last may be shorter)."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _extract_text(resp: Any) -> str:
    """Pull message content from a LiteLLM response (object or dict shaped)."""
    return extract_content_text(resp, strict=False)


def _is_schema_unsupported_error(err: Exception) -> bool:
    """Best-effort: did the strict json_schema request fail *because the provider
    doesn't support it* (vs. an auth/network/quota error)?

    Only a capability gap should trigger the json_object fallback; every other
    error must propagate so it isn't masked by a second attempt. LiteLLM surfaces
    a provider's rejection of response_format/json_schema as a 400-class
    BadRequestError whose message references the schema or response format.
    """
    # Rate-limit / quota errors have their own retry and must propagate if
    # exhausted -- never treat them as a capability gap.
    if is_rate_limit_error(err):
        return False
    msg = str(err).lower()
    if any(
        token in msg
        for token in (
            "response_format",
            "response format",
            "json_schema",
            "json schema",
            "schema",
            "not supported",
            "unsupported",
            "does not support",
        )
    ):
        return True
    status = (
        getattr(err, "status_code", None)
        or getattr(err, "status", None)
        or getattr(err, "code", None)
    )
    return status == 400


class LLMClassifier:
    """Stage 2 classifier: ChangeRecord -> ClassifyResult via a cheap LLM."""

    def __init__(self, config: NoiseFilterConfig) -> None:
        self.config = config
        self._litellm = get_litellm()
        self._max_retries, self._retry_sleep_seconds = retry_policy()

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
            return [_infra_failure() for _ in batch]
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
        except (
            Exception
        ) as e:  # noqa: BLE001 -- inspect; fall back only on a capability gap
            if not _is_schema_unsupported_error(e):
                # Auth/network/quota/etc. -- propagate; a json_object retry would
                # only mask the real error.
                raise
            logger.warning(
                "strict json_schema unsupported for model=%s (%s); "
                "retrying in json_object mode",
                self.config.llm_model,
                e,
            )
            resp = self._completion_with_retry(
                messages=messages, response_format={"type": "json_object"}
            )
        return _extract_text(resp)

    def _completion_with_retry(self, **kwargs: Any) -> Any:
        return litellm_completion(
            model=self.config.llm_model,
            client=self._litellm,
            max_retries=self._max_retries,
            retry_sleep_seconds=self._retry_sleep_seconds,
            temperature=0.0,
            **kwargs,
        )

    def _parse(self, text: str, n: int) -> list[ClassifyResult]:
        verdicts = [_uncertain(MALFORMED_OUTPUT) for _ in range(n)]
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
    "LLM_CALL_FAILED",
    "MALFORMED_OUTPUT",
    "LLMClassifier",
    "is_infra_failure",
]
