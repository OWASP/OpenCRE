"""Isolation + MCP reachability for the OWASP metadata agent."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from unittest.mock import patch

from application.mcp.owasp_agent_tools import (
    call_owasp_meta_tool,
    list_owasp_meta_tool_names,
)
from application.mcp.server import dispatch_tool
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Chapter, Project
from application.utils.owasp_agent.sync import sync_all


class TestOwaspAgentIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "agent.sqlite")
        os.environ["OWASP_AGENT_DB"] = self.db_path
        os.environ["OWASP_AGENT_ENABLED"] = "1"
        store = IndexStore(self.db_path)
        store.upsert_chapter(
            Chapter(
                key="los-angeles",
                name="OWASP Los Angeles",
                city="Los Angeles",
                latitude=34.05,
                longitude=-118.25,
                url="https://nest.example/la",
                source="nest",
            )
        )
        store.upsert_project(
            Project(
                key="zap",
                name="ZAP",
                tags=["appsec"],
                source="nest",
                url="https://nest.example/zap",
            )
        )
        self.store = store

    def tearDown(self) -> None:
        for key in ("OWASP_AGENT_DB", "OWASP_AGENT_ENABLED"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def test_mcp_meta_tools_listed_when_enabled(self) -> None:
        names = list_owasp_meta_tool_names()
        self.assertIn("owasp_meta_ask", names)
        self.assertTrue(all(n.startswith("owasp_meta_") for n in names))

    def test_mcp_meta_tools_hidden_when_disabled(self) -> None:
        os.environ["OWASP_AGENT_ENABLED"] = "0"
        self.assertEqual(list_owasp_meta_tool_names(), [])

    def test_mcp_ask_does_not_return_cre_table(self) -> None:
        data = call_owasp_meta_tool(
            "owasp_meta_ask", {"prompt": "How many OWASP chapters are there?"}
        )
        self.assertEqual(data["channel"], "owasp_meta")
        self.assertIn("response", data)
        self.assertTrue(data["ok"], msg=data)
        # No CRE document table leakage
        self.assertNotIn("table", data)
        self.assertIn("citations", data.get("owasp_agent") or data)

    def test_mcp_count_projects(self) -> None:
        data = dispatch_tool("owasp_meta_count_projects", {"topic": "appsec"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["channel"], "owasp_meta")
        self.assertGreaterEqual(data["data"]["count"], 1)

    def test_mcp_defers_cre_questions(self) -> None:
        data = call_owasp_meta_tool(
            "owasp_meta_ask",
            {"prompt": "How should I store passwords securely?"},
        )
        self.assertFalse(data["ok"])
        self.assertIn("CRE", data["message"])

    def test_sync_never_imports_cre_defs(self) -> None:
        # Guardrail: sync module must not depend on Credoctypes/Node writers.
        import application.utils.owasp_agent.sync as sync_mod
        import application.utils.owasp_agent.concepts as concepts_mod

        for mod in (sync_mod, concepts_mod):
            with open(mod.__file__, encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn("Credoctypes", src)
            self.assertNotIn("cre_defs", src)
            self.assertNotIn("Node_collection", src)

    def test_sync_and_concepts_never_import_shared_database(self) -> None:
        # sync.py and concepts.py only talk to the owasp_agent IndexStore. On
        # the sync path, embed_sync.py is the single module that bridges to the
        # shared application.database (the opt-in meta-embedding push), so it is
        # deliberately not checked here.
        import application.utils.owasp_agent.sync as sync_mod
        import application.utils.owasp_agent.concepts as concepts_mod

        for mod in (sync_mod, concepts_mod):
            with open(mod.__file__, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=mod.__file__)
            offenders = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    offenders += [
                        a.name
                        for a in node.names
                        if a.name == "application.database"
                        or a.name.startswith("application.database.")
                    ]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        offenders.append("." * node.level + base)
                    elif base == "application.database" or base.startswith(
                        "application.database."
                    ):
                        offenders.append(base)
                    elif base == "application":
                        offenders += [
                            "application." + a.name
                            for a in node.names
                            if a.name == "database"
                        ]
            self.assertEqual(
                offenders,
                [],
                msg=f"{mod.__name__} must not import application.database: {offenders}",
            )


if __name__ == "__main__":
    unittest.main()
