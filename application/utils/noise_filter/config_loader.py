"""Module B configuration loader.

Reads the CRE_NOISE_FILTER_* environment variables into a typed, frozen
NoiseFilterConfig. Mirrors the upstream convention (prompt_client.py reads
CRE_* vars inline via os.environ) rather than threading Module B config
through the Flask Config class -- Module B runs as a standalone CLI gate and
does not depend on the Flask app config object.

Retry tuning is intentionally NOT a Module B concern: the Stage 2 classifier
reuses the upstream CRE_LLM_MAX_RETRIES / CRE_LLM_RETRY_SLEEP_SECONDS vars
(read in llm_classifier.py) so noise filtering and the chatbot share one
retry policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Cheap, dedicated classification model. Decoupled from CRE_LLM_CHAT_MODEL by
# design: Module B is the cheap gate and must not pull in the chatbot's
# heavier model.
DEFAULT_LLM_MODEL = "gemini/gemini-2.5-flash-lite"
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_CHARS = 1500
DEFAULT_CONFIDENCE_THRESHOLD = 0.8


@dataclass(frozen=True)
class NoiseFilterConfig:
    """Resolved Module B settings for the Stage 2 classifier."""

    llm_model: str = DEFAULT_LLM_MODEL
    batch_size: int = DEFAULT_BATCH_SIZE
    max_chars: int = DEFAULT_MAX_CHARS
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


def load_config() -> NoiseFilterConfig:
    """Build a NoiseFilterConfig from the CRE_NOISE_FILTER_* environment."""
    return NoiseFilterConfig(
        llm_model=os.environ.get("CRE_NOISE_FILTER_LLM_MODEL", DEFAULT_LLM_MODEL),
        batch_size=int(
            os.environ.get("CRE_NOISE_FILTER_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))
        ),
        max_chars=int(
            os.environ.get("CRE_NOISE_FILTER_MAX_CHARS", str(DEFAULT_MAX_CHARS))
        ),
        confidence_threshold=float(
            os.environ.get(
                "CRE_NOISE_FILTER_CONFIDENCE_THRESHOLD",
                str(DEFAULT_CONFIDENCE_THRESHOLD),
            )
        ),
    )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_MAX_CHARS",
    "NoiseFilterConfig",
    "load_config",
]
