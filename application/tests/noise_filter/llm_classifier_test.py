"""Tests for application.utils.noise_filter.llm_classifier.

Uses unittest (project-wide discovery pattern). The LLM is fully mocked --
no network calls. We swap LLMClassifier._litellm with a Mock and assert on
the messages it receives and how responses are parsed back into verdicts.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from application.utils.noise_filter.config_loader import NoiseFilterConfig
from application.utils.noise_filter.llm_classifier import LLMClassifier
from application.utils.noise_filter.prompts import (
    FEW_SHOT_EXAMPLES,
    SYSTEM_PROMPT_WITH_EXAMPLES,
)
from application.utils.noise_filter.schemas import ChangeRecord


# --- Helpers --------------------------------------------------------------


def _record(text: str = "some security text", heading_path=None) -> ChangeRecord:
    return ChangeRecord.model_validate(
        {
            "schema_version": "0.2.0",
            "chunk_id": "chk:test",
            "artifact_id": "art:test",
            "pipeline_run_id": "20260618T000000Z",
            "text": text,
            "span": {"index": 0, "total": 1, "heading_path": heading_path or []},
            "source": {
                "type": "github",
                "repo": "OWASP/test",
                "commit_sha": "abc123",
                "committed_at": "2026-06-18T00:00:00Z",
            },
            "locator": {"kind": "repo_path", "id": "p.md", "path": "p.md"},
        }
    )


def _resp(content) -> SimpleNamespace:
    """A LiteLLM-shaped response wrapping `content` (str or dict)."""
    text = content if isinstance(content, str) else json.dumps(content)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _classifier(batch_size: int = 10, max_chars: int = 1500) -> LLMClassifier:
    clf = LLMClassifier(NoiseFilterConfig(batch_size=batch_size, max_chars=max_chars))
    clf._retry_sleep_seconds = 0
    return clf


# --- Prompt content -------------------------------------------------------


class PromptContentTests(unittest.TestCase):

    def test_system_prompt_states_recall_first_rule(self) -> None:
        for needle in (
            "KNOWLEDGE",
            "NOISE",
            "UNCERTAIN",
            "When in doubt",
            "Recall matters more than precision",
        ):
            self.assertIn(needle, SYSTEM_PROMPT_WITH_EXAMPLES)

    def test_all_few_shot_examples_embedded(self) -> None:
        for ex in FEW_SHOT_EXAMPLES:
            # First line of each example (newline-free, so it survives the
            # JSON encoding the prompt applies) should appear verbatim.
            needle = ex["text"].split("\n", 1)[0][:40]
            self.assertIn(needle, SYSTEM_PROMPT_WITH_EXAMPLES)

    def test_few_shot_label_distribution(self) -> None:
        labels = [e["label"] for e in FEW_SHOT_EXAMPLES]
        self.assertEqual(labels.count("KNOWLEDGE"), 5)
        self.assertEqual(labels.count("NOISE"), 3)
        self.assertEqual(labels.count("UNCERTAIN"), 2)


# --- Batch ordering / splitting -------------------------------------------


class BatchOrderingTests(unittest.TestCase):

    def test_out_of_order_results_mapped_by_index(self) -> None:
        clf = _classifier(batch_size=3)
        clf._litellm = Mock(
            completion=lambda **kw: _resp(
                {
                    "results": [
                        {
                            "index": 2,
                            "label": "UNCERTAIN",
                            "confidence": 0.5,
                            "reasoning": "c",
                        },
                        {
                            "index": 0,
                            "label": "KNOWLEDGE",
                            "confidence": 0.9,
                            "reasoning": "a",
                        },
                        {
                            "index": 1,
                            "label": "NOISE",
                            "confidence": 0.8,
                            "reasoning": "b",
                        },
                    ]
                }
            )
        )
        out = clf.classify_batch([_record(), _record(), _record()])
        self.assertEqual([v.label for v in out], ["KNOWLEDGE", "NOISE", "UNCERTAIN"])

    def test_batches_split_by_size(self) -> None:
        clf = _classifier(batch_size=2)
        calls = []

        def completion(**kw):
            calls.append(kw)
            n = kw["messages"][1]["content"].count('"index"')
            return _resp(
                {
                    "results": [
                        {
                            "index": i,
                            "label": "KNOWLEDGE",
                            "confidence": 0.9,
                            "reasoning": "x",
                        }
                        for i in range(n)
                    ]
                }
            )

        clf._litellm = Mock(completion=completion)
        out = clf.classify_batch([_record() for _ in range(5)])
        self.assertEqual(len(out), 5)
        self.assertEqual(len(calls), 3)  # 2 + 2 + 1
        self.assertTrue(all(v.label == "KNOWLEDGE" for v in out))


# --- Malformed output -----------------------------------------------------


class MalformedOutputTests(unittest.TestCase):

    def _single(self, content):
        clf = _classifier()
        clf._litellm = Mock(completion=lambda **kw: _resp(content))
        return clf.classify_batch([_record()])[0]

    def test_non_json_marks_uncertain(self) -> None:
        v = self._single("not json at all")
        self.assertEqual(
            (v.label, v.confidence, v.reasoning),
            ("UNCERTAIN", 0.0, "malformed_output"),
        )

    def test_missing_entry_marks_uncertain(self) -> None:
        v = self._single({"results": []})
        self.assertEqual((v.label, v.confidence), ("UNCERTAIN", 0.0))

    def test_invalid_label_marks_uncertain(self) -> None:
        v = self._single(
            {
                "results": [
                    {"index": 0, "label": "SPAM", "confidence": 0.9, "reasoning": "x"}
                ]
            }
        )
        self.assertEqual((v.label, v.confidence), ("UNCERTAIN", 0.0))

    def test_out_of_range_confidence_marks_uncertain(self) -> None:
        v = self._single(
            {
                "results": [
                    {
                        "index": 0,
                        "label": "KNOWLEDGE",
                        "confidence": 9.9,
                        "reasoning": "x",
                    }
                ]
            }
        )
        self.assertEqual((v.label, v.confidence), ("UNCERTAIN", 0.0))

    def test_empty_content_marks_uncertain(self) -> None:
        v = self._single("")
        self.assertEqual((v.label, v.confidence), ("UNCERTAIN", 0.0))


# --- Strict-schema -> json_object fallback --------------------------------


class FallbackTests(unittest.TestCase):

    def test_strict_failure_falls_back_to_json_object(self) -> None:
        clf = _classifier()
        formats = []

        def completion(**kw):
            formats.append(kw["response_format"]["type"])
            if kw["response_format"]["type"] == "json_schema":
                raise ValueError("provider does not support strict schema")
            return _resp(
                {
                    "results": [
                        {
                            "index": 0,
                            "label": "KNOWLEDGE",
                            "confidence": 0.9,
                            "reasoning": "x",
                        }
                    ]
                }
            )

        clf._litellm = Mock(completion=completion)
        out = clf.classify_batch([_record()])
        self.assertEqual(out[0].label, "KNOWLEDGE")
        self.assertEqual(formats, ["json_schema", "json_object"])

    def test_non_capability_error_does_not_fall_back(self) -> None:
        """A non-schema error must propagate, not trigger a json_object retry."""
        clf = _classifier()
        formats = []

        def completion(**kw):
            formats.append(kw["response_format"]["type"])
            raise ValueError("authentication token invalid")  # not a capability gap

        clf._litellm = Mock(completion=completion)
        out = clf.classify_batch([_record()])
        # No fallback attempt; the error surfaces as a failed batch.
        self.assertEqual(formats, ["json_schema"])
        self.assertEqual(out[0].label, "UNCERTAIN")
        self.assertEqual(out[0].reasoning, "llm_call_failed")


# --- Rate-limit retry -----------------------------------------------------


class RetryTests(unittest.TestCase):

    def test_rate_limit_retried_then_succeeds(self) -> None:
        clf = _classifier()
        clf._max_retries = 2
        ok = _resp(
            {
                "results": [
                    {"index": 0, "label": "NOISE", "confidence": 0.9, "reasoning": "x"}
                ]
            }
        )
        clf._litellm = Mock(
            completion=Mock(side_effect=[Exception("HTTP 429 too many requests"), ok])
        )
        with patch("application.utils.noise_filter.llm_classifier.time.sleep"):
            out = clf.classify_batch([_record()])
        self.assertEqual(out[0].label, "NOISE")
        self.assertEqual(clf._litellm.completion.call_count, 2)

    def test_rate_limit_exhausted_marks_batch_failed(self) -> None:
        clf = _classifier()
        clf._max_retries = 1
        clf._litellm = Mock(
            completion=Mock(side_effect=Exception("HTTP 429 too many requests"))
        )
        with patch("application.utils.noise_filter.llm_classifier.time.sleep"):
            out = clf.classify_batch([_record(), _record()])
        self.assertEqual([v.label for v in out], ["UNCERTAIN", "UNCERTAIN"])
        self.assertEqual(
            [v.reasoning for v in out], ["llm_call_failed", "llm_call_failed"]
        )


# --- Truncation -----------------------------------------------------------


class TruncationTests(unittest.TestCase):

    def test_long_text_is_truncated_before_send(self) -> None:
        clf = _classifier(max_chars=50)
        captured = {}

        def completion(**kw):
            captured["user"] = kw["messages"][1]["content"]
            return _resp(
                {
                    "results": [
                        {
                            "index": 0,
                            "label": "KNOWLEDGE",
                            "confidence": 0.9,
                            "reasoning": "x",
                        }
                    ]
                }
            )

        clf._litellm = Mock(completion=completion)
        clf.classify_batch([_record(text="A" * 500)])
        self.assertIn("…[truncated]", captured["user"])
        self.assertNotIn("A" * 100, captured["user"])  # full text not sent


if __name__ == "__main__":
    unittest.main()
