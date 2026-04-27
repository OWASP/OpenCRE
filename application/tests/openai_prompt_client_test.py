"""Tests for OpenAI prompt client helper parsing."""

import unittest

from application.prompt_client.openai_prompt_client import _parse_structured_json_text


class TestOpenAIPromptClientHelpers(unittest.TestCase):
    def test_parse_structured_json_text_parses_clean_json(self) -> None:
        out = _parse_structured_json_text('{"start_bid":"b0"}')
        self.assertEqual(out["start_bid"], "b0")

    def test_parse_structured_json_text_parses_fenced_json(self) -> None:
        out = _parse_structured_json_text('```json\n{"start_bid":"b1"}\n```')
        self.assertEqual(out["start_bid"], "b1")

    def test_parse_structured_json_text_parses_prefixed_json(self) -> None:
        out = _parse_structured_json_text(
            'Here is the JSON you requested:\n{"start_bid":"b2"}'
        )
        self.assertEqual(out["start_bid"], "b2")

    def test_parse_structured_json_text_rejects_non_object_json(self) -> None:
        with self.assertRaises(ValueError):
            _parse_structured_json_text('["not","an","object"]')


if __name__ == "__main__":
    unittest.main()
