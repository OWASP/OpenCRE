import os
import unittest
from unittest import mock

from application import create_app, sqla
from application.utils.comprehension.answer import ABSTAIN_MESSAGE


class UnverifiedChatAnswerTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "NO_LOAD_GRAPH_DB": "1",
                "OWASP_AGENT_ENABLED": "0",
                "INSECURE_REQUESTS": "1",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _chat(self, generated):
        handler = mock.MagicMock()
        handler.generate_text.return_value = generated
        with mock.patch(
            "application.prompt_client.prompt_client.PromptHandler",
            return_value=handler,
        ):
            return (
                self.app.test_client()
                .post("/rest/v1/completion", json={"prompt": "who started opencre"})
                .get_json()
            )

    def test_a_free_form_answer_without_a_matching_source_is_replaced_by_an_honest_refusal(
        self,
    ):
        out = self._chat(
            {
                "response": "OpenCRE was started by the Cloud Security Alliance.",
                "table": "x",
                "accurate": False,
            }
        )
        self.assertEqual(out["response"], ABSTAIN_MESSAGE)
        self.assertNotIn("Cloud Security Alliance", str(out))
        self.assertFalse(out["accurate"])

    def test_an_answer_backed_by_a_matching_node_is_kept(self):
        out = self._chat({"response": "CRE 616-305 is about X.", "accurate": True})
        self.assertEqual(out["response"], "CRE 616-305 is about X.")

    def test_the_switch_restores_the_old_behaviour(self):
        with mock.patch.dict(os.environ, {"CHAT_BLOCK_UNVERIFIED": "0"}):
            out = self._chat({"response": "free text", "accurate": False})
        self.assertEqual(out["response"], "free text")
