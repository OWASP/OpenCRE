"""Load MCP tool input schemas from the committed OpenAPI document.

OpenAPI is the source of truth for selected allowlisted operations' parameters.
This module does not enumerate OpenAPI to decide which tools exist.
"""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

import yaml

from application.mcp.catalog import PUBLIC_TOOLS, ToolSpec, get_tool

# Response-format switchers that can leave JSON; omit from MCP v1 inputs.
_JSON_UNSAFE_QUERY_PARAMS: Set[str] = {"format"}

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_OPENAPI_PATH = os.path.join(REPO_ROOT, "docs", "api", "openapi.yaml")


class OpenAPILookupError(LookupError):
    """Raised when an allowlisted method/path is missing or unusable in OpenAPI."""


def _load_spec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "paths" not in data:
        raise OpenAPILookupError(f"Invalid OpenAPI document: {path}")
    return data


def _resolve_ref(spec: Dict[str, Any], node: Any) -> Any:
    """Resolve local #/components/... refs one level deep as needed."""
    if not isinstance(node, dict):
        return node
    if "$ref" not in node:
        return {key: _resolve_ref(spec, value) for key, value in node.items()}
    ref = node["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise OpenAPILookupError(f"Unsupported OpenAPI $ref: {ref}")
    current: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise OpenAPILookupError(f"Unresolved OpenAPI $ref: {ref}")
        current = current[part]
    # Merge sibling keywords onto the resolved target (OpenAPI 3.0.3).
    resolved = copy.deepcopy(current)
    if isinstance(resolved, dict):
        for key, value in node.items():
            if key == "$ref":
                continue
            resolved[key] = value
        return _resolve_ref(spec, resolved)
    return resolved


def _parameter_to_json_schema(
    spec: Dict[str, Any], param: Dict[str, Any]
) -> Dict[str, Any]:
    schema = param.get("schema")
    if schema is None and "content" in param:
        raise OpenAPILookupError(
            f"Unsupported content-based parameter '{param.get('name')}'"
        )
    if schema is None:
        schema = {"type": "string"}
    resolved = _resolve_ref(spec, schema)
    if not isinstance(resolved, dict):
        raise OpenAPILookupError(
            f"Parameter '{param.get('name')}' schema must be an object"
        )
    out = copy.deepcopy(resolved)
    description = param.get("description")
    if description and "description" not in out:
        out["description"] = description
    return out


def operation_input_schema(
    tool: ToolSpec, *, spec: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build a JSON Schema object for MCP tool arguments from OpenAPI parameters."""
    document = spec if spec is not None else load_openapi_spec()
    method, path = tool.openapi_identity
    paths = document.get("paths") or {}
    path_item = paths.get(path)
    if not isinstance(path_item, dict):
        raise OpenAPILookupError(
            f"Allowlisted OpenAPI path missing: {method.upper()} {path}"
        )
    operation = path_item.get(method)
    if not isinstance(operation, dict):
        raise OpenAPILookupError(
            f"Allowlisted OpenAPI operation missing: {method.upper()} {path}"
        )

    properties: Dict[str, Any] = {}
    required: List[str] = []
    for raw_param in operation.get("parameters") or []:
        param = _resolve_ref(document, raw_param)
        if not isinstance(param, dict):
            raise OpenAPILookupError(f"Invalid parameter on {method.upper()} {path}")
        location = param.get("in")
        name = param.get("name")
        if not name or location not in ("path", "query"):
            continue
        if location == "query" and name in _JSON_UNSAFE_QUERY_PARAMS:
            continue
        properties[name] = _parameter_to_json_schema(document, param)
        if param.get("required"):
            required.append(name)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


@lru_cache(maxsize=1)
def load_openapi_spec(path: str = DEFAULT_OPENAPI_PATH) -> Dict[str, Any]:
    return _load_spec(path)


def clear_openapi_cache() -> None:
    load_openapi_spec.cache_clear()


def input_schema_for_tool(name: str) -> Dict[str, Any]:
    return operation_input_schema(get_tool(name))


def all_tool_input_schemas() -> Dict[str, Dict[str, Any]]:
    """Resolve input schemas for every allowlisted tool (fails if OpenAPI drifts)."""
    spec = load_openapi_spec()
    return {tool.name: operation_input_schema(tool, spec=spec) for tool in PUBLIC_TOOLS}


def openapi_has_operation(method: str, path: str) -> bool:
    spec = load_openapi_spec()
    path_item = (spec.get("paths") or {}).get(path)
    if not isinstance(path_item, dict):
        return False
    return isinstance(path_item.get(method.lower()), dict)
