"""Low-level MCP stdio server for OpenCRE public REST tools."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from application.mcp.catalog import PUBLIC_TOOLS
from application.mcp.openapi_loader import all_tool_input_schemas
from application.mcp.rest_client import (
    RestClient,
    RestClientError,
    RestRequestError,
    RestResponseError,
)

logger = logging.getLogger(__name__)

SERVER_NAME = "opencre"
SERVER_VERSION = "0.1.0"
SERVER_INSTRUCTIONS = (
    "OpenCRE MCP v1 exposes public JSON REST reads only. "
    "Authenticated MyOpenCRE, chat, and admin tools are out of scope."
)


def build_server(rest_client: Optional[RestClient] = None) -> Server[Any]:
    """Create an MCP Server with OpenAPI-derived tool schemas and REST dispatch."""
    client = rest_client or RestClient()
    # Resolve schemas once at startup so OpenAPI drift fails before serving.
    schemas = all_tool_input_schemas()

    async def on_list_tools(
        ctx: Any, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        del ctx, params
        tools = [
            types.Tool(
                name=tool.name,
                description=tool.summary,
                input_schema=schemas[tool.name],
                annotations=types.ToolAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=True,
                ),
            )
            for tool in PUBLIC_TOOLS
        ]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(
        ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del ctx
        name = params.name
        arguments: Dict[str, Any] = dict(params.arguments or {})
        try:
            # schemas is built from the allowlist at startup; unknown names stop here.
            if name not in schemas:
                raise RestRequestError(f"Unknown MCP tool: {name}")
            result = client.call_tool(name, arguments)
            payload = json.dumps(result.data, ensure_ascii=False, default=str)
            structured: Dict[str, Any]
            if isinstance(result.data, dict):
                structured = result.data
            else:
                structured = {"result": result.data}
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=payload)],
                structured_content=structured,
                is_error=False,
            )
        except RestResponseError as exc:
            logger.info("REST error for tool %s: %s", name, exc)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True,
            )
        except RestRequestError as exc:
            logger.info("Bad tool request for %s: %s", name, exc)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True,
            )
        except RestClientError as exc:
            logger.exception("REST client failure for tool %s", name)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Unexpected MCP tool failure for %s", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="Internal MCP tool error.")
                ],
                is_error=True,
            )

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def run_stdio(rest_client: Optional[RestClient] = None) -> None:
    server = build_server(rest_client=rest_client)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def dispatch_tool(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    *,
    rest_client: Optional[RestClient] = None,
) -> Any:
    """Synchronous helper used by tests: catalog → REST, return decoded JSON."""
    client = rest_client or RestClient()
    return client.call_tool(tool_name, arguments or {}).data
