"""The web chatbot and MCP ask share one entry point: same routing, same answer, same failures."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from application import create_app, sqla
from application.mcp.ask import ask
from application.utils.owasp_agent.service import OwaspAgentUnavailable

AGENT_RESPONSE = {
    "response": "Answer: three maturity levels per practice [1].",
    "accurate": True,
    "owasp_agent": {
        "ok": True,
        "citations": ["https://github.com/OWASP/samm/blob/HEAD/a.md"],
        "data": {"evidence": [{"n": 1, "path": "a.md", "snippet": "three levels"}]},
    },
}


class ChatAskParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "NO_LOAD_GRAPH_DB": "1",
                "OWASP_AGENT_ENABLED": "1",
                "INSECURE_REQUESTS": "1",
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _router(self, handle):
        router = MagicMock()
        router.handle.side_effect = handle
        return (
            patch(
                "application.utils.owasp_agent.OwaspAgentRouter", return_value=router
            ),
            router,
        )

    def test_same_question_same_answer_and_citations(self):
        history = [
            {"role": "user", "content": "tell me about SAMM"},
            {"role": "assistant", "content": "ok"},
        ]
        patcher, router = self._router(lambda prompt, history=None: AGENT_RESPONSE)
        with patcher:
            chat = (
                self.app.test_client()
                .post(
                    "/rest/v1/completion",
                    json={
                        "prompt": "How many levels does SAMM have?",
                        "messages": history,
                    },
                )
                .get_json()
            )
            via_ask = ask("How many levels does SAMM have?", history=history)
        self.assertEqual(chat["response"], via_ask["message"])
        self.assertEqual(chat["owasp_agent"]["citations"], via_ask["citations"])
        self.assertEqual(
            via_ask["evidence"], AGENT_RESPONSE["owasp_agent"]["data"]["evidence"]
        )
        # Both routed through the one router with the conversation history.
        for call in router.handle.call_args_list:
            self.assertEqual(call.kwargs.get("history"), history)

    def test_agent_failure_on_a_meta_question_is_refused_by_both(self):
        def boom(prompt, history=None):
            raise RuntimeError("router crashed")

        patcher, _ = self._router(boom)
        with patcher:
            chat = self.app.test_client().post(
                "/rest/v1/completion", json={"prompt": "Who leads the Berlin chapter?"}
            )
            via_ask = ask("Who leads the Berlin chapter?")
        self.assertEqual(chat.status_code, 503)
        self.assertFalse(via_ask["ok"])
        self.assertIn("temporary problem", via_ask["message"])

    def test_service_returns_none_when_disabled(self):
        from application.utils.owasp_agent.service import route_question

        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}):
            self.assertIsNone(route_question("anything"))
        self.assertTrue(issubclass(OwaspAgentUnavailable, Exception))
