"""Local stdio MCP server exposing public OpenCRE REST reads (issue #1003 v1)."""

from application.mcp.catalog import PUBLIC_TOOLS, get_tool, list_tool_names

__all__ = ["PUBLIC_TOOLS", "get_tool", "list_tool_names"]
