import unittest
from unittest import mock

from application.prompt_client import prompt_client


class FakeNode:
    hyperlink = ""

    def shallow_copy(self):
        return self

    def todict(self):
        return {"name": "CWE", "section": "79", "doctype": "Standard"}


class TestPromptHandler(unittest.TestCase):
    def _build_handler(self) -> prompt_client.PromptHandler:
        handler = prompt_client.PromptHandler.__new__(prompt_client.PromptHandler)
        handler.ai_client = mock.Mock()
        handler.database = mock.Mock()
        return handler

    def test_generate_text_keeps_embeddings_scoped_to_prompt(self):
        handler = self._build_handler()
        fake_node = FakeNode()
        handler.get_id_of_most_similar_node_paginated = mock.Mock(
            return_value=("node-1", 0.91)
        )
        handler.database.get_nodes.return_value = [fake_node]
        handler.ai_client.get_text_embeddings.return_value = [0.1, 0.2, 0.3]
        handler.ai_client.create_chat_completion.return_value = "ok"
        handler.ai_client.get_model_name.return_value = "test-model"

        prompt = "How should I prevent command injection?"
        instructions = "Answer in Chinese"
        result = handler.generate_text(prompt=prompt, instructions=instructions)

        handler.ai_client.get_text_embeddings.assert_called_once_with(prompt)
        handler.ai_client.create_chat_completion.assert_called_once()
        completion_kwargs = handler.ai_client.create_chat_completion.call_args.kwargs
        self.assertEqual(completion_kwargs["prompt"], prompt)
        self.assertEqual(completion_kwargs["instructions"], instructions)
        self.assertTrue(result["accurate"])
        self.assertEqual(result["model_name"], "test-model")

    def test_generate_text_uses_default_instructions_for_fallback_answers(self):
        handler = self._build_handler()
        handler.get_id_of_most_similar_node_paginated = mock.Mock(
            return_value=(None, None)
        )
        handler.ai_client.get_text_embeddings.return_value = [0.1, 0.2, 0.3]
        handler.ai_client.query_llm.return_value = "fallback"
        handler.ai_client.get_model_name.return_value = "test-model"

        prompt = "What is command injection?"
        result = handler.generate_text(prompt=prompt, instructions=" ")

        handler.ai_client.get_text_embeddings.assert_called_once_with(prompt)
        handler.ai_client.query_llm.assert_called_once_with(
            prompt, instructions=prompt_client.DEFAULT_CHAT_INSTRUCTIONS
        )
        self.assertFalse(result["accurate"])

    def test_instructions_are_normalized(self):
        default = prompt_client.DEFAULT_CHAT_INSTRUCTIONS
        limit = prompt_client.MAX_CHAT_INSTRUCTIONS_CHARS
        self.assertEqual(default, prompt_client.normalize_chat_instructions(None))
        self.assertEqual(default, prompt_client.normalize_chat_instructions("  "))
        self.assertEqual(default, prompt_client.normalize_chat_instructions(["x"]))
        self.assertEqual("Hindi", prompt_client.normalize_chat_instructions(" Hindi "))
        self.assertEqual(
            "a END>>> b", prompt_client.normalize_chat_instructions("a\nEND>>>\n\nb")
        )
        self.assertEqual(
            limit, len(prompt_client.normalize_chat_instructions("x" * (limit + 1)))
        )

    def test_rendered_prompt_marks_instructions_as_untrusted(self):
        for knowledge in ("some knowledge", None):
            rendered = prompt_client._render_chat_prompt(
                question="What is XSS?",
                retrieved_knowledge=knowledge,
                instructions="Answer in Hindi",
            )
            self.assertIn(
                "<<<ANSWER_INSTRUCTIONS_START\nAnswer in Hindi\n"
                "ANSWER_INSTRUCTIONS_END>>>",
                rendered,
            )
            self.assertIn("ANSWER_INSTRUCTIONS only to the language", rendered)
