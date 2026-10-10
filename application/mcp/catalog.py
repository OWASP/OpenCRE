"""Static security allowlist for OpenCRE MCP tools.

Exposure is determined only by this allowlist — never by enumerating OpenAPI.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Authenticated tools stay hidden unless a deployment opts in, so the public
# surface is identical whether or not anyone has logged in on this machine.
AUTH_TOOLS_ENV = "OPENCRE_MCP_AUTH_TOOLS"
_TRUE_VALUES = {"1", "true", "yes"}


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool bound to a fixed REST operation."""

    name: str
    method: str
    path_template: str
    summary: str
    auth: bool = False
    read_only: bool = True
    scopes: Tuple[str, ...] = field(default=())

    @property
    def openapi_identity(self) -> Tuple[str, str]:
        """(HTTP method lowercased, OpenAPI path) used to resolve schemas."""
        return (self.method.lower(), self.path_template)


# Exact v1 surface approved for the first MCP PR (public JSON reads only).
PUBLIC_TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_cre_by_id",
        method="GET",
        path_template="/rest/v1/id/{creid}",
        summary="Get a CRE by ID",
    ),
    ToolSpec(
        name="get_cre_by_name",
        method="GET",
        path_template="/rest/v1/name/{crename}",
        summary="Get a CRE by name",
    ),
    ToolSpec(
        name="get_node",
        method="GET",
        path_template="/rest/v1/{ntype}/{name}",
        summary="Get nodes by type and name",
    ),
    ToolSpec(
        name="get_documents_by_tag",
        method="GET",
        path_template="/rest/v1/tags",
        summary="Get documents by tag",
    ),
    ToolSpec(
        name="text_search",
        method="GET",
        path_template="/rest/v1/text_search",
        summary="Text search",
    ),
    ToolSpec(
        name="list_root_cres",
        method="GET",
        path_template="/rest/v1/root_cres",
        summary="Get root CREs",
    ),
    ToolSpec(
        name="list_all_cres",
        method="GET",
        path_template="/rest/v1/all_cres",
        summary="List all CREs (paginated)",
    ),
    ToolSpec(
        name="list_standards",
        method="GET",
        path_template="/rest/v1/standards",
        summary="List standards",
    ),
    ToolSpec(
        name="list_ga_standards",
        method="GET",
        path_template="/rest/v1/ga_standards",
        summary="Standards eligible for gap analysis",
    ),
)

AUTHENTICATED_TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_my_resources",
        method="GET",
        path_template="/rest/v1/user/resources",
        summary="Get your saved standards selection",
        auth=True,
        scopes=("myopencre:read",),
    ),
    ToolSpec(
        name="set_my_resources",
        method="PUT",
        path_template="/rest/v1/user/resources",
        summary="Replace your saved standards selection",
        auth=True,
        read_only=False,
        scopes=("myopencre:write",),
    ),
)

_TOOLS_BY_NAME: Dict[str, ToolSpec] = {
    tool.name: tool for tool in PUBLIC_TOOLS + AUTHENTICATED_TOOLS
}


def auth_tools_enabled() -> bool:
    return os.environ.get(AUTH_TOOLS_ENV, "").strip().lower() in _TRUE_VALUES


def list_tool_names() -> List[str]:
    return [tool.name for tool in PUBLIC_TOOLS]


def get_tool(name: str) -> ToolSpec:
    try:
        return _TOOLS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"Unknown MCP tool: {name}") from exc


def active_tools() -> Tuple[ToolSpec, ...]:
    """Tools this process serves: public always, authenticated on opt-in."""
    if auth_tools_enabled():
        return PUBLIC_TOOLS + AUTHENTICATED_TOOLS
    return PUBLIC_TOOLS
