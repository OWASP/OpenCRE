"""Integration: /rest/v1/completion routes to OWASP agent when enabled."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from application import create_app, sqla  # type: ignore
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Chapter
from application.utils.owasp_agent.queries import MetaQueries
from application.utils.owasp_agent.router import OwaspAgentRouter


class TestCompletionOwaspAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "agent.sqlite")
        store = IndexStore(self.db_path)
        store.upsert_chapter(
            Chapter(
                key="los-angeles",
                name="OWASP Los Angeles",
                city="Los Angeles",
                latitude=34.05,
                longitude=-118.25,
                source="nest",
                url="https://nest.owasp.org/chapters/los-angeles",
            )
        )
        self.store = store
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        os.environ["INSECURE_REQUESTS"] = "True"
        os.environ["NO_LOGIN"] = "1"
        os.environ["OWASP_AGENT_ENABLED"] = "1"
        os.environ["OWASP_AGENT_DB"] = self.db_path
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        for key in ("NO_LOGIN", "OWASP_AGENT_ENABLED", "OWASP_AGENT_DB"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def test_completion_uses_agent_for_chapter_count(self) -> None:
        queries = MetaQueries(self.store, geocode_fn=lambda p: (34.0, -118.0))
        router = OwaspAgentRouter(store=self.store, queries=queries)
        with patch(
            "application.utils.owasp_agent.OwaspAgentRouter", return_value=router
        ), patch("application.prompt_client.prompt_client.PromptHandler") as mock_ph:
            mock_ph.return_value.generate_text.side_effect = AssertionError(
                "CRE RAG should not run for meta questions"
            )
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "How many OWASP chapters are there?"},
                    content_type="application/json",
                )
        self.assertEqual(200, response.status_code)
        data = json.loads(response.data)
        self.assertIn("owasp-agent-router", data.get("model_name", ""))
        self.assertIn("1", data["response"])

    def test_completion_falls_through_for_normative(self) -> None:
        with patch("application.prompt_client.prompt_client.PromptHandler") as mock_ph:
            mock_ph.return_value.generate_text.return_value = {
                "response": "Answer: use a password manager",
                "table": [],
                "accurate": True,
                "model_name": "test-llm",
            }
            with self.app.test_client() as client:
                response = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "How should I store passwords securely?"},
                    content_type="application/json",
                )
        self.assertEqual(200, response.status_code)
        data = json.loads(response.data)
        self.assertEqual(data["model_name"], "test-llm")
