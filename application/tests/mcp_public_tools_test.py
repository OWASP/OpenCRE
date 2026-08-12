"""Tests for OpenCRE MCP v1 public REST tools (issue #1003)."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict
from unittest.mock import patch

import networkx as nx

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.mcp import catalog
from application.mcp.catalog import PUBLIC_TOOLS, get_tool, list_tool_names
from application.mcp.openapi_loader import (
    OpenAPILookupError,
    all_tool_input_schemas,
    clear_openapi_cache,
    input_schema_for_tool,
    load_openapi_spec,
    operation_input_schema,
)
from application.mcp.rest_client import (
    RestClient,
    RestRequestError,
    RestResponseError,
    flask_test_session,
)
from application.mcp.server import build_server, dispatch_tool

import mcp.types as types


APPROVED_TOOLS = [
    "get_cre_by_id",
    "get_cre_by_name",
    "get_node",
    "get_documents_by_tag",
    "text_search",
    "list_root_cres",
    "list_all_cres",
    "list_standards",
    "list_ga_standards",
]


class McpPublicToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        os.environ["INSECURE_REQUESTS"] = "True"
        sqla.create_all()
        self.collection = db.Node_collection().with_graph()
        self.collection.graph.with_graph(graph=nx.DiGraph(), graph_data=[])
        clear_openapi_cache()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        clear_openapi_cache()

    def _rest(self) -> RestClient:
        return RestClient(session=flask_test_session(self.app.test_client()))

    def _seed_cre_and_node(self) -> Dict[str, Any]:
        cre = defs.CRE(id="111-111", description="CA", name="CA", tags=["ta"])
        node = defs.Standard(
            name="ASVS",
            section="1.1",
            subsection="",
            sectionID="1.1",
            hyperlink="https://example.com/asvs",
        )
        self.collection.add_cre(cre)
        self.collection.add_node(node)
        return {"cre": cre, "node": node}

    # --- A. Catalog / security boundary ---

    def test_catalog_exposes_exactly_nine_approved_tools(self) -> None:
        names = list_tool_names()
        self.assertEqual(names, APPROVED_TOOLS)
        self.assertEqual(len(PUBLIC_TOOLS), 9)
        for tool in PUBLIC_TOOLS:
            self.assertEqual(tool.method.upper(), "GET")

    def test_catalog_excludes_auth_admin_writes_and_heavy_reads(self) -> None:
        names = set(list_tool_names())
        forbidden = {
            "get_user_resources",
            "put_user_resources",
            "user_resources",
            "completion",
            "map_analysis",
            "map_analysis_weak_links",
            "get_ma_job_results",
            "fetch_job",
            "get_cre_csv",
            "get_config",
            "health",
            "deeplink",
            "admin_import_runs",
        }
        self.assertTrue(names.isdisjoint(forbidden))
        for tool in PUBLIC_TOOLS:
            self.assertNotIn("/user/resources", tool.path_template)
            self.assertNotIn("completion", tool.path_template)
            self.assertNotIn("/admin/", tool.path_template)
            self.assertNotIn("map_analysis", tool.path_template)
            self.assertNotIn("cre_csv", tool.path_template)
            self.assertNotIn("health", tool.path_template)
            self.assertNotIn("deeplink", tool.path_template)
            self.assertNotIn("section/", tool.path_template)
            self.assertNotIn("sectionid/", tool.path_template)

    def test_unknown_tool_rejected(self) -> None:
        with self.assertRaises(KeyError):
            get_tool("not_a_real_tool")
        with self.assertRaises(RestRequestError):
            self._rest().call_tool("not_a_real_tool", {})

    def test_arbitrary_path_and_base_url_impossible(self) -> None:
        client = self._rest()
        with self.assertRaises(RestRequestError):
            client.call_tool(
                "get_cre_by_id",
                {"creid": "../admin", "path": "/rest/v1/user/resources"},
            )
        with self.assertRaises(RestRequestError):
            client.call_tool(
                "get_cre_by_id", {"creid": "111-111", "base_url": "http://evil"}
            )
        # Path traversal / separator injection
        with self.assertRaises(RestRequestError):
            client.call_tool("get_cre_by_id", {"creid": "a/b"})
        with self.assertRaises(RestRequestError):
            client.call_tool("get_node", {"ntype": "Standard", "name": "x?y=1"})

    def test_get_node_rejects_user_resources_collision(self) -> None:
        """ntype=user/name=resources must not reach MyOpenCRE REST."""
        client = self._rest()
        with self.assertRaises(RestRequestError):
            client.call_tool("get_node", {"ntype": "user", "name": "resources"})
        with self.assertRaises(RestRequestError):
            client.call_tool("get_node", {"ntype": "User", "name": "resources"})
        with self.assertRaises(RestRequestError):
            client.call_tool("get_node", {"ntype": "completion", "name": "x"})

    def test_format_query_param_rejected(self) -> None:
        client = self._rest()
        with self.assertRaises(RestRequestError):
            client.call_tool("get_cre_by_id", {"creid": "111-111", "format": "csv"})
        with self.assertRaises(RestRequestError):
            client.call_tool("text_search", {"text": "x", "format": "md"})

    # --- B. OpenAPI source of truth ---

    def test_every_catalog_entry_resolves_openapi_operation(self) -> None:
        spec = load_openapi_spec()
        for tool in PUBLIC_TOOLS:
            method, path = tool.openapi_identity
            self.assertIn(path, spec["paths"])
            self.assertIn(method, spec["paths"][path])
            schema = operation_input_schema(tool, spec=spec)
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema.get("additionalProperties", True))

    def test_input_schemas_reflect_openapi_parameters_without_format(self) -> None:
        cre_schema = input_schema_for_tool("get_cre_by_id")
        self.assertIn("creid", cre_schema["required"])
        self.assertIn("creid", cre_schema["properties"])
        self.assertIn("source", cre_schema["properties"])
        self.assertIn("include_only", cre_schema["properties"])
        self.assertNotIn("format", cre_schema["properties"])

        tag_schema = input_schema_for_tool("get_documents_by_tag")
        self.assertIn("tag", tag_schema["required"])
        self.assertEqual(tag_schema["properties"]["tag"]["type"], "array")
        self.assertNotIn("format", tag_schema["properties"])

        node_schema = input_schema_for_tool("get_node")
        for key in ("ntype", "name"):
            self.assertIn(key, node_schema["required"])
        self.assertIn("section", node_schema["properties"])
        self.assertNotIn("format", node_schema["properties"])

        standards_schema = input_schema_for_tool("list_standards")
        self.assertIn("all", standards_schema["properties"])
        self.assertEqual(standards_schema["properties"]["all"]["type"], "boolean")

        emptyish = input_schema_for_tool("list_ga_standards")
        self.assertEqual(emptyish.get("properties"), {})

    def test_missing_allowlisted_openapi_path_fails_clearly(self) -> None:
        fake = catalog.ToolSpec(
            name="ghost",
            method="GET",
            path_template="/rest/v1/does-not-exist",
            summary="ghost",
        )
        with self.assertRaises(OpenAPILookupError):
            operation_input_schema(fake)

    def test_non_allowlisted_openapi_get_is_not_an_mcp_tool(self) -> None:
        spec = load_openapi_spec()
        self.assertIn("/rest/v1/map_analysis", spec["paths"])
        self.assertIn("/rest/v1/user/resources", spec["paths"])
        self.assertIn("/rest/v1/health", spec["paths"])
        names = set(list_tool_names())
        self.assertNotIn("map_analysis", names)
        self.assertEqual(len(all_tool_input_schemas()), 9)

    # --- C. REST parity ---

    def test_parity_get_cre_by_id(self) -> None:
        seeded = self._seed_cre_and_node()
        cre = seeded["cre"]
        with self.app.test_client() as flask_client:
            rest = flask_client.get(f"/rest/v1/id/{cre.id}")
            mcp_data = dispatch_tool(
                "get_cre_by_id",
                {"creid": cre.id},
                rest_client=RestClient(session=flask_test_session(flask_client)),
            )
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(mcp_data, rest.get_json())

    def test_parity_get_node(self) -> None:
        seeded = self._seed_cre_and_node()
        node = seeded["node"]
        with self.app.test_client() as flask_client:
            rest = flask_client.get(f"/rest/v1/Standard/{node.name}")
            mcp_data = dispatch_tool(
                "get_node",
                {"ntype": "Standard", "name": node.name},
                rest_client=RestClient(session=flask_test_session(flask_client)),
            )
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(mcp_data, rest.get_json())

    def test_parity_text_search(self) -> None:
        self._seed_cre_and_node()
        with self.app.test_client() as flask_client:
            rest = flask_client.get("/rest/v1/text_search?text=CA")
            mcp_data = dispatch_tool(
                "text_search",
                {"text": "CA"},
                rest_client=RestClient(session=flask_test_session(flask_client)),
            )
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(mcp_data, rest.get_json())

    def test_parity_list_root_cres_and_all_cres(self) -> None:
        cre = defs.CRE(id="222-222", description="Root", name="RootCRE")
        self.collection.add_cre(cre)
        with self.app.test_client() as flask_client:
            client = RestClient(session=flask_test_session(flask_client))
            root_rest = flask_client.get("/rest/v1/root_cres")
            root_mcp = dispatch_tool("list_root_cres", {}, rest_client=client)
            all_rest = flask_client.get("/rest/v1/all_cres")
            all_mcp = dispatch_tool("list_all_cres", {}, rest_client=client)
        self.assertEqual(root_rest.status_code, 200)
        self.assertEqual(root_mcp, root_rest.get_json())
        self.assertEqual(all_rest.status_code, 200)
        self.assertEqual(all_mcp, all_rest.get_json())

    def test_parity_list_standards(self) -> None:
        self._seed_cre_and_node()
        with self.app.test_client() as flask_client:
            rest = flask_client.get("/rest/v1/standards")
            mcp_data = dispatch_tool(
                "list_standards",
                {},
                rest_client=RestClient(session=flask_test_session(flask_client)),
            )
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(mcp_data, rest.get_json())

    def test_parity_remaining_tools(self) -> None:
        cre = defs.CRE(
            id="333-333", description="Tagged", name="Tagged", tags=["alpha"]
        )
        self.collection.add_cre(cre)
        with self.app.test_client() as flask_client:
            client = RestClient(session=flask_test_session(flask_client))
            by_name_rest = flask_client.get("/rest/v1/name/Tagged")
            by_name_mcp = dispatch_tool(
                "get_cre_by_name", {"crename": "Tagged"}, rest_client=client
            )
            tags_rest = flask_client.get("/rest/v1/tags?tag=alpha")
            tags_mcp = dispatch_tool(
                "get_documents_by_tag", {"tag": ["alpha"]}, rest_client=client
            )
            ga_rest = flask_client.get("/rest/v1/ga_standards")
            ga_mcp = dispatch_tool("list_ga_standards", {}, rest_client=client)
        self.assertEqual(by_name_mcp, by_name_rest.get_json())
        self.assertEqual(tags_mcp, tags_rest.get_json())
        self.assertEqual(ga_mcp, ga_rest.get_json())

    # --- D. Error behavior ---

    def test_rest_404_is_tool_failure_not_empty_success(self) -> None:
        client = self._rest()
        with self.assertRaises(RestResponseError) as ctx:
            client.call_tool("get_cre_by_id", {"creid": "999-999"})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_missing_required_input_fails(self) -> None:
        client = self._rest()
        with self.assertRaises(RestRequestError):
            client.call_tool("text_search", {})
        with self.assertRaises(RestRequestError):
            client.call_tool("get_documents_by_tag", {})
        with self.assertRaises(RestRequestError):
            client.call_tool("get_node", {"ntype": "Standard"})

    def test_default_http_session_disables_trust_env(self) -> None:
        """Production session must not pick up env/.netrc credentials."""
        client = RestClient()
        self.assertFalse(getattr(client._session, "trust_env", True))

    def test_openapi_schema_rejects_wrong_parameter_types_before_http(self) -> None:
        """OpenAPI-derived types are enforced; invalid args never hit REST."""
        client = self._rest()
        tag_schema = input_schema_for_tool("get_documents_by_tag")
        self.assertEqual(tag_schema["properties"]["tag"]["type"], "array")
        with self.assertRaises(RestRequestError) as tag_ctx:
            client.call_tool("get_documents_by_tag", {"tag": "not-an-array"})
        self.assertIn("Invalid arguments", str(tag_ctx.exception))

        standards_schema = input_schema_for_tool("list_standards")
        self.assertEqual(standards_schema["properties"]["all"]["type"], "boolean")
        with self.assertRaises(RestRequestError) as all_ctx:
            client.call_tool("list_standards", {"all": "true"})
        self.assertIn("Invalid arguments", str(all_ctx.exception))

        # Confirm rejection happens before the HTTP adapter is invoked.
        class _NoHttpSession:
            cookies = None

            def get(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("HTTP must not be called for invalid schema args")

        guarded = RestClient(session=_NoHttpSession())
        with self.assertRaises(RestRequestError):
            guarded.call_tool("get_documents_by_tag", {"tag": "scalar"})
        with self.assertRaises(RestRequestError):
            guarded.call_tool("list_standards", {"all": "yes"})

    # --- E. Server list/call smoke (in-process) ---

    def test_server_lists_and_calls_tool(self) -> None:
        self._seed_cre_and_node()
        client = self._rest()
        server = build_server(rest_client=client)

        async def _run() -> None:
            list_handler = server.get_request_handler("tools/list")
            self.assertIsNotNone(list_handler)
            assert list_handler is not None
            listed_raw = await list_handler.handler(None, None)
            assert isinstance(listed_raw, types.ListToolsResult)
            tool_names = [tool.name for tool in listed_raw.tools]
            self.assertEqual(tool_names, APPROVED_TOOLS)
            for tool in listed_raw.tools:
                self.assertNotIn("format", (tool.input_schema.get("properties") or {}))

            call_handler = server.get_request_handler("tools/call")
            self.assertIsNotNone(call_handler)
            assert call_handler is not None

            result_raw = await call_handler.handler(
                None,
                types.CallToolRequestParams(
                    name="get_cre_by_id", arguments={"creid": "111-111"}
                ),
            )
            assert isinstance(result_raw, types.CallToolResult)
            self.assertFalse(result_raw.is_error)
            first = result_raw.content[0]
            assert isinstance(first, types.TextContent)
            payload = json.loads(first.text)
            self.assertIn("data", payload)

            missing_raw = await call_handler.handler(
                None,
                types.CallToolRequestParams(
                    name="get_cre_by_id", arguments={"creid": "no-such"}
                ),
            )
            assert isinstance(missing_raw, types.CallToolResult)
            self.assertTrue(missing_raw.is_error)

            unknown_raw = await call_handler.handler(
                None,
                types.CallToolRequestParams(name="map_analysis", arguments={}),
            )
            assert isinstance(unknown_raw, types.CallToolResult)
            self.assertTrue(unknown_raw.is_error)

        import asyncio

        asyncio.run(_run())

    def test_unexpected_internal_errors_are_sanitized(self) -> None:
        """Unexpected exceptions are logged server-side but not leaked to MCP clients."""
        sensitive = "SENSITIVE_INTERNAL_MARKER_do_not_leak"

        class _BoomSession:
            cookies = None

            def get(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError(sensitive)

        server = build_server(rest_client=RestClient(session=_BoomSession()))

        async def _run() -> None:
            call_handler = server.get_request_handler("tools/call")
            self.assertIsNotNone(call_handler)
            assert call_handler is not None
            result_raw = await call_handler.handler(
                None,
                types.CallToolRequestParams(name="list_ga_standards", arguments={}),
            )
            assert isinstance(result_raw, types.CallToolResult)
            self.assertTrue(result_raw.is_error)
            first = result_raw.content[0]
            assert isinstance(first, types.TextContent)
            self.assertEqual(first.text, "Internal MCP tool error.")
            self.assertNotIn(sensitive, first.text)

        import asyncio

        with self.assertLogs("application.mcp.server", level="ERROR"):
            asyncio.run(_run())

    def test_base_url_comes_from_env_not_tool_args(self) -> None:
        with patch.dict(os.environ, {"OPENCRE_BASE_URL": "http://example.test:9"}):
            client = RestClient()
            self.assertEqual(client.base_url, "http://example.test:9")


if __name__ == "__main__":
    unittest.main()
