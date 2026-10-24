"""Low-level MCP stdio server for OpenCRE public REST tools + optional OWASP meta."""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
from typing import Any, Dict, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from application.mcp.ask import ASK_TOOL, RATE_TOOL, ask as run_ask, rate_answer
from application.mcp.catalog import active_tools, auth_tools_enabled
from application.mcp.openapi_loader import input_schemas_for
from application.mcp.owasp_agent_tools import (
    OWASP_META_TOOLS,
    call_owasp_meta_tool,
    get_owasp_meta_tool,
    list_owasp_meta_tool_names,
)
from application.mcp.rest_client import (
    RestClient,
    RestClientError,
    RestRequestError,
    RestResponseError,
)
from application.utils.owasp_agent import is_owasp_agent_enabled


SERVER_NAME = "opencre"
SERVER_VERSION = "0.1.0"
ASK_TOOL_NAME = ASK_TOOL["name"]
RATE_TOOL_NAME = RATE_TOOL["name"]


def server_instructions() -> str:
    """Describe the live tool surface (v1/v2, ask, optional OWASP meta tools)."""
    if auth_tools_enabled():
        served = active_tools()
        has_write = any(not tool.read_only for tool in served)
        if has_write:
            base = (
                "OpenCRE MCP v2 exposes public JSON REST reads plus authenticated "
                "MyOpenCRE tools (including set_my_resources for writes). "
                "Chat and admin tools remain out of scope."
            )
        else:
            base = (
                "OpenCRE MCP v2 exposes public JSON REST reads plus authenticated "
                "MyOpenCRE read tools. Chat and admin tools remain out of scope."
            )
    else:
        base = (
            "OpenCRE MCP v1 exposes public JSON REST reads for CREs/standards. "
            "Authenticated MyOpenCRE, chat, and admin tools remain out of scope."
        )
    base += (
        " The ask tool returns structured facts only (CRE and/or OWASP metadata); "
        "the host synthesizes narrative answers via multiple tool calls."
    )
    if is_owasp_agent_enabled():
        return (
            base
            + " When OWASP_AGENT_ENABLED is set, additional owasp_meta_* tools answer "
            "community/metadata questions from a separate index — not the CRE graph."
        )
    return base


_BLOCKING_LIMITER: Any = None


async def run_blocking_with_app(fn: Any) -> Any:
    """Run a blocking call in a worker thread so one slow question cannot stall the server.

    ``ask`` takes seconds (LLM calls). Called straight from an async handler it blocks the
    event loop, so parallel users are answered one after another. Each call gets its own Flask
    app context (database sessions are scoped per context and must not be shared across
    threads); without a Flask app (stdio mode) it runs inline.
    """
    global _BLOCKING_LIMITER
    try:
        from flask import current_app

        app = current_app._get_current_object()  # type: ignore[attr-defined]
    except RuntimeError:
        return fn()

    import anyio

    if _BLOCKING_LIMITER is None:
        try:
            cap = max(1, int(os.environ.get("OPENCRE_MCP_ASK_CONCURRENCY", "8")))
        except ValueError:
            cap = 8
        _BLOCKING_LIMITER = anyio.CapacityLimiter(cap)

    def _call() -> Any:
        with app.app_context():
            return fn()

    return await anyio.to_thread.run_sync(_call, limiter=_BLOCKING_LIMITER)


def build_server(rest_client: Optional[RestClient] = None) -> Server[Any]:
    """Create an MCP Server with OpenAPI-derived tool schemas and REST dispatch."""
    client = rest_client or RestClient()
    served = active_tools()
    # Resolve schemas once at startup so OpenAPI drift fails before serving.
    schemas = input_schemas_for(served)

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
                    read_only_hint=tool.read_only,
                    destructive_hint=not tool.read_only,
                    idempotent_hint=True,
                    open_world_hint=True,
                ),
            )
            for tool in served
        ]
        # Local fact router — always available (security path needs no OWASP agent).
        tools.append(
            types.Tool(
                name=ASK_TOOL["name"],
                description=ASK_TOOL["summary"],
                input_schema=ASK_TOOL["input_schema"],
                annotations=types.ToolAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=True,
                ),
            )
        )
        # Optional OWASP metadata channel (chat/MCP only — not CRE REST).
        if is_owasp_agent_enabled():
            for meta in OWASP_META_TOOLS:
                tools.append(
                    types.Tool(
                        name=meta["name"],
                        description=meta["summary"],
                        input_schema=meta["input_schema"],
                        annotations=types.ToolAnnotations(
                            read_only_hint=True,
                            destructive_hint=False,
                            idempotent_hint=True,
                            open_world_hint=True,
                        ),
                    )
                )
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(
        ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del ctx
        name = params.name
        arguments: Dict[str, Any] = dict(params.arguments or {})
        try:
            from application.mcp import remote_auth

            if remote_auth.remote_mode_enabled():
                # Every tool needs a signed-in account with the role it requires.
                try:
                    caller = remote_auth.require_remote_auth(name, frozenset(schemas))
                except remote_auth.RemoteAskAuthError as auth_exc:
                    return types.CallToolResult(
                        content=[types.TextContent(type="text", text=str(auth_exc))],
                        is_error=True,
                    )
                if name == ASK_TOOL_NAME and caller is not None:
                    from application.utils import rate_limit, roles

                    try:
                        rate_limit.check_and_count(
                            caller.email, roles.role_for(caller.email), "ask"
                        )
                    except rate_limit.RateLimited as limited:
                        return types.CallToolResult(
                            content=[
                                types.TextContent(
                                    type="text", text=f"429 {limited.message()}"
                                )
                            ],
                            is_error=True,
                        )
            if name == ASK_TOOL_NAME:
                data = await run_blocking_with_app(
                    lambda: run_ask(
                        str(arguments.get("prompt") or ""),
                        corpus=str(arguments.get("corpus") or "auto"),
                        place=(
                            str(arguments["place"])
                            if arguments.get("place") is not None
                            else None
                        ),
                        history=arguments.get("history"),
                        rest_client=client,
                    )
                )
                payload = json.dumps(data, ensure_ascii=False, default=str)
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=payload)],
                    structured_content=(
                        data if isinstance(data, dict) else {"result": data}
                    ),
                    is_error=False,
                )
            if name == RATE_TOOL_NAME:
                data = rate_answer(
                    str(arguments.get("answer_id") or ""),
                    str(arguments.get("rating") or ""),
                    str(arguments["comment"]) if arguments.get("comment") else None,
                )
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=json.dumps(data))],
                    structured_content=data,
                    is_error=False,
                )
            if get_owasp_meta_tool(name) is not None:
                if name.startswith("owasp_meta_sources_"):
                    data = await run_blocking_with_app(
                        lambda: call_owasp_meta_tool(name, arguments)
                    )
                else:
                    data = call_owasp_meta_tool(name, arguments)
                payload = json.dumps(data, ensure_ascii=False, default=str)
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=payload)],
                    structured_content=(
                        data if isinstance(data, dict) else {"result": data}
                    ),
                    is_error=False,
                )
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
        except KeyError as exc:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True,
            )
        except ValueError as exc:
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
        instructions=server_instructions(),
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
    """Synchronous helper used by tests: catalog → REST or local tools."""
    args = dict(arguments or {})
    if tool_name == ASK_TOOL_NAME:
        return run_ask(
            str(args.get("prompt") or ""),
            corpus=str(args.get("corpus") or "auto"),
            place=str(args["place"]) if args.get("place") is not None else None,
            rest_client=rest_client,
        )
    if tool_name == RATE_TOOL_NAME:
        return rate_answer(
            str(args.get("answer_id") or ""),
            str(args.get("rating") or ""),
            str(args["comment"]) if args.get("comment") else None,
        )
    if tool_name in list_owasp_meta_tool_names() or get_owasp_meta_tool(tool_name):
        return call_owasp_meta_tool(tool_name, args)
    client = rest_client or RestClient()
    return client.call_tool(tool_name, args).data
