"""Multi-turn chat: the conversation is background for a follow-up, never a second question.

Each scripted conversation in data/multiturn_conversations.json is run through the real router with a
scripted rewrite model; we check what the answer pipeline actually receives. (scripts/ops/multiturn_probe.py
runs the same conversations against a live deployment.)
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from application.tests.owasp_agent.owasp_agent_test import _seed_store
from application.utils.owasp_agent.queries import MetaQueries
from application.utils.owasp_agent.router import OwaspAgentRouter

CONVERSATIONS = json.loads(
    (Path(__file__).parent / "data" / "multiturn_conversations.json").read_text()
)


class MultiTurnConversationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = _seed_store(os.path.join(self.tmp.name, "agent.sqlite"))
        self.router = OwaspAgentRouter(
            store=store, queries=MetaQueries(store, geocode_fn=lambda p: (0.0, 0.0))
        )
        env = mock.patch.dict(
            os.environ,
            {
                "OWASP_AGENT_ENABLED": "1",
                "OWASP_AGENT_SIM_ROUTER": "0",
                "OWASP_HISTORY_MODE": "",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)

    def _run(self, convo):
        seen = []
        calls = []

        def fake_rewriter(model, **kwargs):
            def rewrite(system, user):
                calls.append(user)
                if convo["rewrite"] == "__FAIL__":
                    raise RuntimeError("503 model down")
                return convo["rewrite"] or ""

            return rewrite

        def record(prompt):
            seen.append(prompt)
            return prompt

        with mock.patch(
            "application.prompt_client.litellm_router.system_user_fn",
            side_effect=fake_rewriter,
        ), mock.patch(
            "application.utils.owasp_agent.prompt_normalize.normalize_prompt",
            side_effect=record,
        ):
            self.router.handle(convo["next"], history=convo["history"])
        return seen, calls

    def test_each_conversation_answers_only_its_own_question(self):
        for convo in CONVERSATIONS:
            with self.subTest(convo["name"]):
                seen, calls = self._run(convo)
                self.assertTrue(seen, "the answer pipeline never received the question")
                received = seen[0]
                self.assertEqual(received, convo["expect_standalone"])
                for forbidden in convo["must_not_contain"]:
                    self.assertNotIn(forbidden, received.lower())
                self.assertEqual(len(calls), convo["rewrite_calls"])

    def test_the_rewrite_prompt_carries_the_history_as_background_and_the_last_message(
        self,
    ):
        convo = CONVERSATIONS[0]
        _, calls = self._run(convo)
        self.assertIn("user: Does the exchange cover agentic AI?", calls[0])
        self.assertIn("assistant: Yes, the AI Exchange covers agentic AI", calls[0])
        self.assertIn("Last message: What are some key risks", calls[0])

    def test_a_long_conversation_only_sends_the_recent_turns_to_the_rewrite(self):
        history = []
        for i in range(10):
            history += [
                {"role": "user", "content": f"question number {i}"},
                {"role": "assistant", "content": f"answer number {i}"},
            ]
        convo = {**CONVERSATIONS[0], "history": history}
        _, calls = self._run(convo)
        self.assertNotIn("question number 0", calls[0])
        self.assertIn("answer number 9", calls[0])


class ProbeEvaluationTest(unittest.TestCase):
    def test_repeating_the_previous_answer_or_missing_the_topic_fails(self):
        from scripts.ops.multiturn_probe import evaluate

        first = (
            "Answer: The AI Exchange covers agentic AI threats and controls in depth."
        )
        self.assertEqual(
            evaluate(
                first,
                "Key risks include prompt injection and excessive agency.",
                ["risk"],
            ),
            [],
        )
        self.assertTrue(evaluate(first, first, ["risk"]))  # same text again
        self.assertTrue(evaluate(first, "Something unrelated.", ["risk"]))


class NativeHistoryTest(unittest.TestCase):
    def setUp(self):
        from application.utils.comprehension import synthesize as syn

        self.syn = syn
        self.addCleanup(syn.set_history, [])

    def test_history_becomes_real_turns_between_system_and_the_final_message(self):
        self.syn.set_history(
            [
                {"role": "user", "content": "Does the exchange cover agentic AI?"},
                {"role": "assistant", "content": "Yes."},
            ]
        )
        out = self.syn.with_history(
            [
                {"role": "system", "content": "S"},
                {"role": "user", "content": "Sources...\n\nQuestion: key risks?"},
            ]
        )
        self.assertEqual(
            [m["role"] for m in out], ["system", "user", "assistant", "user"]
        )
        self.assertEqual(out[1]["content"], "Does the exchange cover agentic AI?")
        self.assertIn("Question: key risks?", out[-1]["content"])

    def test_history_is_trimmed_alternating_and_starts_with_a_user_turn(self):
        long = "x" * 5000
        self.syn.set_history(
            [{"role": "assistant", "content": "orphan"}]
            + [
                {"role": "user", "content": long},
                {"role": "user", "content": "second user message"},
            ]
            + [{"role": "assistant", "content": "a"}] * 2
        )
        turns = self.syn.get_history()
        self.assertEqual(
            [t["role"] for t in turns], ["user", "assistant"]
        )  # orphan dropped, same roles merged
        self.assertLessEqual(
            len(turns[0]["content"]), self.syn.MAX_HISTORY_CHARS * 2 + 1
        )

    def test_no_history_leaves_messages_alone_and_the_rule_is_only_added_with_history(
        self,
    ):
        self.syn.set_history([])
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]
        self.assertEqual(self.syn.with_history(msgs), msgs)
        seen = []
        self.syn.synthesize(
            "q", [("body", ["u"])], lambda system, user: seen.append(system) or "A [1]"
        )
        self.assertNotIn(self.syn.HISTORY_RULE, seen[0])
        self.syn.set_history([{"role": "user", "content": "earlier"}])
        self.syn.synthesize(
            "q", [("body", ["u"])], lambda system, user: seen.append(system) or "A [1]"
        )
        self.assertIn(self.syn.HISTORY_RULE, seen[1])

    def test_router_hands_the_history_to_the_answer_call_once_per_turn(self):
        import tempfile

        from application.tests.owasp_agent.owasp_agent_test import _seed_store
        from application.utils.owasp_agent.queries import MetaQueries
        from application.utils.owasp_agent.router import OwaspAgentRouter

        history = [
            {"role": "user", "content": "What is SAMM?"},
            {"role": "assistant", "content": "A maturity model."},
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"OWASP_AGENT_ENABLED": "1", "OWASP_AGENT_SIM_ROUTER": "0"}
        ):
            store = _seed_store(os.path.join(tmp, "a.sqlite"))
            router = OwaspAgentRouter(
                store=store, queries=MetaQueries(store, geocode_fn=lambda p: (0.0, 0.0))
            )
            router.handle("Who leads the Berlin chapter?", history=history)
        self.assertEqual(
            [t["role"] for t in self.syn.get_history()], ["user", "assistant"]
        )
