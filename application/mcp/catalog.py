"""Static security allowlist for OpenCRE MCP v1 public-read tools.

Exposure is determined only by this allowlist — never by enumerating OpenAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool bound to a fixed public REST GET operation."""

    name: str
    method: str
    path_template: str
    summary: str

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

_TOOLS_BY_NAME: Dict[str, ToolSpec] = {tool.name: tool for tool in PUBLIC_TOOLS}


def list_tool_names() -> List[str]:
    return [tool.name for tool in PUBLIC_TOOLS]


def get_tool(name: str) -> ToolSpec:
    try:
        return _TOOLS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"Unknown MCP tool: {name}") from exc
