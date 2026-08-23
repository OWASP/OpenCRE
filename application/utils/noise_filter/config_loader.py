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
# Fraction of a run's classified chunks that must be *infrastructure* failures
# (the LLM call itself failed) for the run to report status="degraded" and exit
# non-zero, so the orchestrator retries the whole run. Default 1.0 = only a total
# wipeout (every classified chunk failed) is degraded; smaller failures leave
# their rows `pending` for a natural retry and still exit 0.
DEFAULT_FAILURE_THRESHOLD = 1.0


@dataclass(frozen=True)
class NoiseFilterConfig:
    """Resolved Module B settings for the Stage 2 classifier."""

    llm_model: str = DEFAULT_LLM_MODEL
    batch_size: int = DEFAULT_BATCH_SIZE
    max_chars: int = DEFAULT_MAX_CHARS
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    failure_threshold: float = DEFAULT_FAILURE_THRESHOLD

    def __post_init__(self) -> None:
        """Fail fast on invalid settings, regardless of construction path.

        Validated here (not only in load_config) so direct constructors --
        e.g. tests -- get the same guarantees. batch_size in particular must
        be >= 1: it becomes the step of range() when batching records.
        """
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")
        if self.max_chars < 1:
            raise ValueError(f"max_chars must be >= 1, got {self.max_chars}")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be in [0.0, 1.0], got "
                f"{self.confidence_threshold}"
            )
        if not 0.0 <= self.failure_threshold <= 1.0:
            raise ValueError(
                f"failure_threshold must be in [0.0, 1.0], got "
                f"{self.failure_threshold}"
            )


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
        failure_threshold=float(
            os.environ.get(
                "CRE_NOISE_FILTER_FAILURE_THRESHOLD",
                str(DEFAULT_FAILURE_THRESHOLD),
            )
        ),
    )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_FAILURE_THRESHOLD",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_MAX_CHARS",
    "NoiseFilterConfig",
    "load_config",
]
