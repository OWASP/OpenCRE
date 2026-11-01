"""Tests for MCP fact-only ``ask`` tool."""

from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from application.mcp import auth as mcp_auth
from application.mcp.ask import (
    ASK_TOOL,
    CORPUS_AUTO,
    CORPUS_OWASP_META,
    CORPUS_SECURITY,
    ask,
)
from application.mcp.rest_client import RestResponseError, RestResult
from application.mcp.server import dispatch_tool, server_instructions
from application.utils.gap_analysis import OPENCRE_STANDARD_NAME
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Chapter


class _FakeRestClient:
    """Minimal RestClient stand-in for security-path unit tests."""

    def __init__(
        self,
        *,
        search: Optional[List[Dict[str, Any]]] = None,
        cres: Optional[Dict[str, Dict[str, Any]]] = None,
        resources: Optional[Dict[str, Any]] = None,
        resources_error: Optional[Exception] = None,
        search_error: Optional[Exception] = None,
    ) -> None:
        self.search = search or []
        self.cres = cres or {}
        self.resources = resources
        self.resources_error = resources_error
        self.search_error = search_error
        self.calls: List[tuple] = []

    def call_tool(self, tool_name: str, arguments=None) -> RestResult:
        args = dict(arguments or {})
        self.calls.append((tool_name, args))
        if tool_name == "text_search":
            if self.search_error is not None:
                raise self.search_error
            return RestResult(200, self.search, "")
        if tool_name == "get_cre_by_id":
            cre_id = args.get("creid")
            payload = self.cres.get(cre_id) or {"data": {"id": cre_id, "links": []}}
            return RestResult(200, payload, "")
        if tool_name == "get_my_resources":
            if self.resources_error is not None:
                raise self.resources_error
            return RestResult(200, self.resources or {"selected": []}, "")
        raise AssertionError(f"unexpected tool {tool_name}")


class McpAskToolTest(unittest.TestCase):
    def test_ask_tool_schema_is_strict(self) -> None:
        schema = ASK_TOOL["input_schema"]
        self.assertFalse(schema.get("additionalProperties", True))
        self.assertIn("prompt", schema["required"])
        self.assertEqual(
            set(schema["properties"]["corpus"]["enum"]),
            {CORPUS_AUTO, CORPUS_SECURITY, CORPUS_OWASP_META},
        )

    def test_server_always_lists_ask(self) -> None:
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}, clear=False):
            instructions = server_instructions()
            self.assertIn("ask tool", instructions.lower())

    @patch("application.mcp.ask.OwaspAgentRouter")
    def test_auto_meta_channel(self, router_cls: MagicMock) -> None:
        router_cls.return_value.handle.return_value = {
            "response": "Answer: 1 chapter",
            "accurate": True,
            "owasp_agent": {
                "ok": True,
                "kind": "count_chapters",
                "data": {"count": 1},
                "citations": ["https://nest.example/la"],
            },
        }
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
            with patch(
                "application.mcp.ask.classify_intent", return_value="count_chapters"
            ):
                out = ask("How many OWASP chapters are there?", corpus=CORPUS_AUTO)

        self.assertTrue(out["ok"])
        self.assertEqual(out["channel"], CORPUS_OWASP_META)
        self.assertEqual(out["intent"], "count_chapters")
        self.assertIn("https://nest.example/la", out["citations"])
        router_cls.return_value.handle.assert_called_once()

    @patch("application.mcp.ask.OwaspAgentRouter")
    def test_meta_runs_before_cre_normative_defer(self, router_cls: MagicMock) -> None:
        """AIX/meta evidence must win even when intent is cre_normative."""
        router_cls.return_value.handle.return_value = {
            "response": "Answer: lethal trifecta …",
            "accurate": True,
            "owasp_agent": {
                "ok": True,
                "kind": "evidence",
                "citations": ["https://owaspai.org/docs/ai_security_overview/"],
            },
        }
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
            with patch(
                "application.mcp.ask.classify_intent", return_value="cre_normative"
            ):
                with patch(
                    "application.mcp.ask._ensure_app",
                    side_effect=RuntimeError("no app in unit test"),
                ):
                    out = ask(
                        "lethal trifecta according to OWASP AI Exchange",
                        corpus=CORPUS_AUTO,
                    )
        self.assertTrue(out["ok"])
        self.assertEqual(out["channel"], CORPUS_OWASP_META)
        self.assertIn("trifecta", out["message"].lower())
        router_cls.return_value.handle.assert_called_once()

    @patch("application.prompt_client.prompt_client.PromptHandler.generate_text")
    def test_auto_security_never_calls_generate_text(
        self, generate_text: MagicMock
    ) -> None:
        cre_doc = {
            "id": "111-111",
            "name": "Password Storage",
            "doctype": "CRE",
            "description": "Store passwords safely",
        }
        enriched = {
            "data": {
                "id": "111-111",
                "name": "Password Storage",
                "doctype": "CRE",
                "description": "Store passwords safely",
                "links": [
                    {
                        "document": {
                            "name": "ASVS",
                            "doctype": "Standard",
                            "section": "2.4.1",
                            "hyperlink": "https://example/asvs",
                        },
                        "ltype": "Linked To",
                    },
                    {
                        "document": {
                            "name": "CWE",
                            "doctype": "Standard",
                            "section": "259",
                            "hyperlink": "https://example/cwe",
                        },
                        "ltype": "Linked To",
                    },
                ],
            }
        }
        client = _FakeRestClient(
            search=[cre_doc],
            cres={"111-111": enriched},
        )
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}, clear=False):
            with patch(
                "application.mcp.ask.classify_intent", return_value="cre_normative"
            ):
                out = ask(
                    "How should I store passwords?",
                    corpus=CORPUS_AUTO,
                    rest_client=client,  # type: ignore[arg-type]
                )

        generate_text.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertEqual(out["channel"], CORPUS_SECURITY)
        self.assertEqual(out["standards_filter"], "all_mapped")
        self.assertEqual(len(out["items"]), 1)
        names = {s["name"] for s in out["items"][0]["standards"]}
        self.assertEqual(names, {"ASVS", "CWE"})
        self.assertIn("https://opencre.org/cre/111-111", out["citations"])

    def test_corpus_security_skips_router(self) -> None:
        client = _FakeRestClient(
            search=[
                {
                    "id": "222-222",
                    "name": "AuthN",
                    "doctype": "CRE",
                }
            ],
            cres={
                "222-222": {
                    "data": {
                        "id": "222-222",
                        "name": "AuthN",
                        "doctype": "CRE",
                        "links": [],
                    }
                }
            },
        )
        with patch("application.mcp.ask.OwaspAgentRouter") as router_cls:
            out = ask(
                "authentication",
                corpus=CORPUS_SECURITY,
                rest_client=client,  # type: ignore[arg-type]
            )
            router_cls.assert_not_called()
        self.assertEqual(out["channel"], CORPUS_SECURITY)
        self.assertTrue(out["ok"])

    def test_corpus_owasp_meta_rejects_cre_looking(self) -> None:
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "1"}, clear=False):
            with patch(
                "application.mcp.ask.classify_intent", return_value="cre_normative"
            ):
                out = ask("How should I store passwords?", corpus=CORPUS_OWASP_META)
        self.assertFalse(out["ok"])
        self.assertEqual(out["channel"], CORPUS_OWASP_META)
        self.assertIn("corpus=security", out["message"])

    def test_myopencre_filter_when_logged_in(self) -> None:
        cre_doc = {"id": "333-333", "name": "Session", "doctype": "CRE"}
        enriched = {
            "data": {
                "id": "333-333",
                "name": "Session",
                "doctype": "CRE",
                "links": [
                    {
                        "document": {
                            "name": "ASVS",
                            "doctype": "Standard",
                            "section": "3.1",
                            "hyperlink": "https://example/asvs",
                        }
                    },
                    {
                        "document": {
                            "name": "CWE",
                            "doctype": "Standard",
                            "section": "613",
                            "hyperlink": "https://example/cwe",
                        }
                    },
                    {
                        "document": {
                            "name": OPENCRE_STANDARD_NAME,
                            "doctype": "Standard",
                            "section": "x",
                            "hyperlink": "https://opencre.org",
                        }
                    },
                ],
            }
        }
        client = _FakeRestClient(
            search=[cre_doc],
            cres={"333-333": enriched},
            resources={"selected": ["ASVS"]},
        )
        with patch(
            "application.mcp.catalog.auth_tools_enabled", return_value=True
        ), patch("application.mcp.auth.current_id_token", return_value="id-token"):
            out = ask(
                "session security",
                corpus=CORPUS_SECURITY,
                rest_client=client,  # type: ignore[arg-type]
            )
        self.assertEqual(out["standards_filter"], "myopencre")
        names = {s["name"] for s in out["items"][0]["standards"]}
        self.assertEqual(names, {"ASVS", OPENCRE_STANDARD_NAME})
        self.assertNotIn("CWE", names)

    def test_myopencre_not_applied_when_logged_out(self) -> None:
        cre_doc = {"id": "444-444", "name": "Crypto", "doctype": "CRE"}
        enriched = {
            "data": {
                "id": "444-444",
                "name": "Crypto",
                "doctype": "CRE",
                "links": [
                    {
                        "document": {
                            "name": "ASVS",
                            "doctype": "Standard",
                            "section": "6.1",
                        }
                    },
                    {
                        "document": {
                            "name": "CWE",
                            "doctype": "Standard",
                            "section": "327",
                        }
                    },
                ],
            }
        }
        client = _FakeRestClient(
            search=[cre_doc],
            cres={"444-444": enriched},
            resources={"selected": ["ASVS"]},
        )
        with patch(
            "application.mcp.catalog.auth_tools_enabled", return_value=True
        ), patch(
            "application.mcp.auth.current_id_token",
            side_effect=mcp_auth.NotAuthenticated("run login"),
        ):
            out = ask(
                "crypto",
                corpus=CORPUS_SECURITY,
                rest_client=client,  # type: ignore[arg-type]
            )
        self.assertEqual(out["standards_filter"], "all_mapped")
        names = {s["name"] for s in out["items"][0]["standards"]}
        self.assertEqual(names, {"ASVS", "CWE"})
        # Must not have attempted get_my_resources without a token.
        self.assertNotIn("get_my_resources", [c[0] for c in client.calls])

    def test_empty_search_is_ok_false(self) -> None:
        client = _FakeRestClient(
            search_error=RestResponseError(404, "No object matches")
        )
        out = ask(
            "zzzz-no-match",
            corpus=CORPUS_SECURITY,
            rest_client=client,  # type: ignore[arg-type]
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["items"], [])

    def test_dispatch_tool_ask(self) -> None:
        client = _FakeRestClient(
            search=[{"id": "555-555", "name": "X", "doctype": "CRE"}],
            cres={
                "555-555": {
                    "data": {
                        "id": "555-555",
                        "name": "X",
                        "doctype": "CRE",
                        "links": [],
                    }
                }
            },
        )
        out = dispatch_tool(
            "ask",
            {"prompt": "X", "corpus": CORPUS_SECURITY},
            rest_client=client,  # type: ignore[arg-type]
        )
        self.assertEqual(out["channel"], CORPUS_SECURITY)

    def test_invalid_corpus_raises(self) -> None:
        with self.assertRaises(ValueError):
            ask("hi", corpus="nope")

    def test_empty_prompt_raises(self) -> None:
        with self.assertRaises(ValueError):
            ask("  ")


class McpAskIntegrationMetaTest(unittest.TestCase):
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

    def tearDown(self) -> None:
        for key in ("OWASP_AGENT_DB", "OWASP_AGENT_ENABLED"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def test_auto_chapter_count_via_real_router(self) -> None:
        out = ask("How many OWASP chapters are there?", corpus=CORPUS_AUTO)
        self.assertEqual(out["channel"], CORPUS_OWASP_META)
        self.assertTrue(out["ok"], msg=out)


if __name__ == "__main__":
    unittest.main()
