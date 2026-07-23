"""Tests for application.utils.noise_filter.config_loader.

Uses unittest to match the project-wide discovery pattern. Covers defaults,
environment overrides, and the NoiseFilterConfig invariants enforced in
__post_init__ (so every construction path -- not just load_config -- fails
fast on bad settings).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application.utils.noise_filter.config_loader import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_LLM_MODEL,
    DEFAULT_MAX_CHARS,
    NoiseFilterConfig,
    load_config,
)

_ENV_KEYS = (
    "CRE_NOISE_FILTER_LLM_MODEL",
    "CRE_NOISE_FILTER_BATCH_SIZE",
    "CRE_NOISE_FILTER_MAX_CHARS",
    "CRE_NOISE_FILTER_CONFIDENCE_THRESHOLD",
)


class LoadConfigTests(unittest.TestCase):

    def test_defaults_when_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            for k in _ENV_KEYS:
                os.environ.pop(k, None)
            cfg = load_config()
        self.assertEqual(cfg.llm_model, DEFAULT_LLM_MODEL)
        self.assertEqual(cfg.batch_size, DEFAULT_BATCH_SIZE)
        self.assertEqual(cfg.max_chars, DEFAULT_MAX_CHARS)
        self.assertEqual(cfg.confidence_threshold, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_env_overrides_applied(self) -> None:
        overrides = {
            "CRE_NOISE_FILTER_LLM_MODEL": "openai/gpt-4o-mini",
            "CRE_NOISE_FILTER_BATCH_SIZE": "5",
            "CRE_NOISE_FILTER_MAX_CHARS": "800",
            "CRE_NOISE_FILTER_CONFIDENCE_THRESHOLD": "0.6",
        }
        with patch.dict(os.environ, overrides):
            cfg = load_config()
        self.assertEqual(cfg.llm_model, "openai/gpt-4o-mini")
        self.assertEqual(cfg.batch_size, 5)
        self.assertEqual(cfg.max_chars, 800)
        self.assertEqual(cfg.confidence_threshold, 0.6)


class InvariantTests(unittest.TestCase):

    def test_valid_config_constructs(self) -> None:
        cfg = NoiseFilterConfig(batch_size=1, max_chars=1, confidence_threshold=0.0)
        self.assertEqual(cfg.batch_size, 1)

    def test_batch_size_below_one_raises(self) -> None:
        with self.assertRaises(ValueError):
            NoiseFilterConfig(batch_size=0)

    def test_max_chars_below_one_raises(self) -> None:
        with self.assertRaises(ValueError):
            NoiseFilterConfig(max_chars=0)

    def test_confidence_above_one_raises(self) -> None:
        with self.assertRaises(ValueError):
            NoiseFilterConfig(confidence_threshold=1.5)

    def test_confidence_below_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            NoiseFilterConfig(confidence_threshold=-0.1)


if __name__ == "__main__":
    unittest.main()
