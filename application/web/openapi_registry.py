"""OpenAPI registration, generation, and guardrail helpers for the public REST API."""

from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Type

import yaml
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from flask import Flask
from marshmallow import Schema, fields

from application.web import openapi_schemas as schemas

API_DESCRIPTION = (
    "Public REST API for OpenCRE (Open Common Requirement Enumeration). "
    "Documents read-only endpoints implemented by the OpenCRE backend."
)

OPENAPI_GUARDRAIL_EXEMPT_RULES: Set[str] = {
    "/rest/v1/openapi.yaml",
    "/rest/v1/login",
    "/rest/v1/callback",
    "/rest/v1/logout",
    "/rest/v1/user",
    "/rest/v1/completion",
    "/rest/v1/cre_csv_import",
    "/api/capabilities",
    "/docs/faq.md",
    "/",
    "/<path:path>",
}

OPENAPI_GUARDRAIL_EXEMPT_PREFIXES: Tuple[str, ...] = (
    "/admin/",
    "/smartlink/",
    "/deeplink/",
)

OPENAPI_IN_SCOPE_PREFIX = "/rest/v1"

# Views that must remain linked to the OpenAPI document (guardrail).
OPENAPI_DOCUMENTED_VIEW_NAMES: Set[str] = set()


class PathSpec:
    __slots__ = (
        "path",
        "method",
        "view_name",
        "tags",
        "summary",
        "description",
        "query_schema",
        "response_schema",
        "not_found",
        "extra_responses",
        "response_override",
        "request_body",
    )

    def __init__(
        self,
        path: str,
        view_name: str,
        *,
        method: str = "get",
        tags: Optional[List[str]] = None,
        summary: str = "",
        description: str = "",
        query_schema: Optional[Type[Schema]] = None,
        response_schema: Optional[Type[Schema]] = None,
        not_found: bool = True,
        extra_responses: Optional[Dict[str, Any]] = None,
        response_override: Optional[Dict[str, Any]] = None,
        request_body: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.path = path
        self.method = method.lower()
        self.view_name = view_name
        self.tags = tags or []
        self.summary = summary
        self.description = description
        self.query_schema = query_schema
        self.response_schema = response_schema
        self.not_found = not_found
        self.extra_responses = extra_responses or {}
        self.response_override = response_override
        self.request_body = request_body


OPENAPI_PATHS: List[PathSpec] = [
    PathSpec(
        "/rest/v1/id/{creid}",
        "find_cre",
        tags=["CRE"],
        summary="Get a CRE by ID",
        description="Retrieve a Common Requirement Enumeration (CRE) by its external ID.",
        query_schema=schemas.FindCREQuerySchema,
        response_schema=schemas.CREResponseSchema,
    ),
    PathSpec(
        "/rest/v1/name/{crename}",
        "find_cre",
        tags=["CRE"],
        summary="Get a CRE by name",
        query_schema=schemas.FindCREQuerySchema,
        response_schema=schemas.CREResponseSchema,
    ),
    PathSpec(
        "/rest/v1/{ntype}/{name}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get nodes by type and name",
        description="Retrieve standards, tools, or other node types by name.",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/standard/{name}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get standard nodes by name",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/{ntype}/{name}/sectionid/{sectionID}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get nodes by section ID",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/{ntype}/{name}/section/{section}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get nodes by section",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/{ntype}/{name}/section/{section}/subsection/{subsection}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get nodes by section and subsection",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/{ntype}/{name}/sectionid/{sectionID}/subsection/{subsection}",
        "find_node_by_name",
        tags=["Nodes"],
        summary="Get nodes by section ID and subsection",
        query_schema=schemas.NodeQuerySchema,
        response_schema=schemas.NodeListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/tags",
        "find_document_by_tag",
        tags=["Tags"],
        summary="Get documents by tag",
        query_schema=schemas.TagQuerySchema,
        response_schema=schemas.DataListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/map_analysis",
        "map_analysis",
        tags=["Gap analysis"],
        summary="Map analysis between two standards",
        description="Returns cached gap analysis or enqueues a background job.",
        query_schema=schemas.MapAnalysisQuerySchema,
        response_schema=schemas.MapAnalysisResponseSchema,
        extra_responses={
            "400": {"description": "Fewer than two standards provided"},
            "503": {"description": "Gap analysis unavailable"},
        },
    ),
    PathSpec(
        "/rest/v1/map_analysis_weak_links",
        "map_analysis_weak_links",
        tags=["Gap analysis"],
        summary="Weak links for a map analysis result",
        query_schema=schemas.MapAnalysisWeakLinksQuerySchema,
        response_schema=schemas.MapAnalysisResponseSchema,
    ),
    PathSpec(
        "/rest/v1/ma_job_results",
        "fetch_job",
        tags=["Gap analysis"],
        summary="Gap analysis background job status/result",
        query_schema=schemas.JobResultsQuerySchema,
        response_schema=schemas.JobStatusResponseSchema,
        extra_responses={"500": {"description": "Job failed"}},
    ),
    PathSpec(
        "/rest/v1/standards",
        "standards",
        tags=["Standards"],
        summary="List standards",
        not_found=False,
        response_override={
            "200": {
                "description": "Standards retrieved",
                "content": {
                    "application/json": {
                        "schema": {"type": "array", "items": {"type": "string"}}
                    }
                },
            }
        },
    ),
    PathSpec(
        "/rest/v1/ga_standards",
        "ga_standards",
        tags=["Gap analysis"],
        summary="Standards eligible for gap analysis",
        not_found=False,
        response_override={
            "200": {
                "description": "Eligible standards retrieved",
                "content": {
                    "application/json": {
                        "schema": {"type": "array", "items": {"type": "string"}}
                    }
                },
            }
        },
    ),
    PathSpec(
        "/rest/v1/text_search",
        "text_search",
        tags=["Search"],
        summary="Text search",
        query_schema=schemas.TextSearchQuerySchema,
        response_schema=schemas.DataListResponseSchema,
        extra_responses={"400": {"description": "Missing text parameter"}},
    ),
    PathSpec(
        "/rest/v1/health",
        "health",
        tags=["Operations"],
        summary="Health check",
        description="Feature-flagged via CRE_ENABLE_HEALTH=1.",
        response_schema=schemas.HealthResponseSchema,
        not_found=True,
        extra_responses={"503": {"description": "Unhealthy"}},
    ),
    PathSpec(
        "/rest/v1/root_cres",
        "find_root_cres",
        tags=["CRE"],
        summary="Get root CREs",
        query_schema=schemas.FormatQuerySchema,
        response_schema=schemas.DataListResponseSchema,
    ),
    PathSpec(
        "/rest/v1/deeplink/{name}",
        "deeplink",
        tags=["Deeplink"],
        summary="Resolve REST deeplink by name",
        description="Redirects to an external hyperlink when found.",
        not_found=True,
    ),
    PathSpec(
        "/rest/v1/deeplink/{ntype}/{name}",
        "deeplink",
        tags=["Deeplink"],
        summary="Resolve REST deeplink by type and name",
        not_found=True,
    ),
    PathSpec(
        "/rest/v1/all_cres",
        "all_cres",
        tags=["CRE"],
        summary="List all CREs (paginated)",
        query_schema=schemas.AllCREsQuerySchema,
        response_schema=schemas.AllCREsResponseSchema,
    ),
    PathSpec(
        "/rest/v1/cre_csv",
        "get_cre_csv",
        tags=["CRE"],
        summary="Download CRE catalogue CSV",
        description="Returns a CSV attachment of the CRE mapping template.",
        not_found=True,
        response_override={
            "200": {
                "description": "CSV file download",
                "content": {
                    "text/csv": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    ),
    PathSpec(
        "/rest/v1/config",
        "get_config",
        tags=["Operations"],
        summary="Public configuration flags",
        response_schema=schemas.ConfigResponseSchema,
        not_found=False,
    ),
    PathSpec(
        "/rest/v1/user/resources",
        "get_user_resources",
        tags=["User"],
        summary="Get the current user's selected standards",
        description=(
            "Requires login and the MyOpenCRE feature; returns an empty "
            "selection when either is disabled."
        ),
        not_found=False,
        response_override={
            "200": {
                "description": "The user's selected standards",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "selected": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                        }
                    }
                },
            }
        },
    ),
    PathSpec(
        "/rest/v1/user/resources",
        "put_user_resources",
        method="put",
        tags=["User"],
        summary="Replace the current user's selected standards",
        not_found=False,
        extra_responses={"400": {"description": "Invalid selection body"}},
        request_body={
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["selected"],
                        "properties": {
                            "selected": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "description": (
                                    "Standard names to select. Non-empty strings; "
                                    "values are trimmed and deduplicated."
                                ),
                            }
                        },
                    }
                }
            },
        },
        response_override={
            "200": {
                "description": "The stored selection",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "selected": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                        }
                    }
                },
            }
        },
    ),
]


def openapi_documented(view_name: str) -> Callable:
    """Decorator marking a Flask view as part of the public OpenAPI surface."""

    def decorator(fn: Callable) -> Callable:
        OPENAPI_DOCUMENTED_VIEW_NAMES.add(view_name)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper._openapi_view_name = view_name  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _marshmallow_query_parameters(schema_cls: Type[Schema]) -> List[Dict[str, Any]]:
    schema = schema_cls()
    params: List[Dict[str, Any]] = []
    for name, field in schema.fields.items():
        param: Dict[str, Any] = {
            "name": name,
            "in": "query",
            "required": field.required,
        }
        if isinstance(field, fields.List):
            param["schema"] = {"type": "array", "items": {"type": "string"}}
            param["style"] = "form"
            param["explode"] = True
            if name == "standard":
                param["schema"]["minItems"] = 2
                param["schema"]["maxItems"] = 2
        elif isinstance(field, fields.Int):
            param["schema"] = {"type": "integer"}
        elif isinstance(field, fields.Bool):
            param["schema"] = {"type": "boolean"}
        else:
            param["schema"] = {"type": "string"}
            if name == "format":
                param["schema"]["enum"] = list(schemas.FORMAT_ENUM)
        desc = field.metadata.get("description")
        if desc:
            param["description"] = desc
        params.append(param)
    return params


def _path_parameters(path: str) -> List[Dict[str, Any]]:
    return [
        {
            "name": match.group(1),
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for match in re.finditer(r"\{([^}]+)\}", path)
    ]


def _ensure_schema_component(
    spec: APISpec, schema_cls: Type[Schema], registered: Set[str]
) -> str:
    schema_name = schema_cls.__name__
    if schema_name not in registered:
        spec.components.schema(schema_name, schema=schema_cls)
        registered.add(schema_name)
    return schema_name


def _operation_from_path(
    path_spec: PathSpec, spec: APISpec, registered_schemas: Set[str]
) -> Dict[str, Any]:
    operation: Dict[str, Any] = {
        "tags": path_spec.tags,
        "summary": path_spec.summary,
    }
    if path_spec.description:
        operation["description"] = path_spec.description

    parameters = _path_parameters(path_spec.path)
    path_names = {param["name"] for param in parameters}
    if path_spec.query_schema is not None:
        query_params = _marshmallow_query_parameters(path_spec.query_schema)
        parameters.extend(
            [param for param in query_params if param["name"] not in path_names]
        )
    if parameters:
        operation["parameters"] = parameters

    if path_spec.request_body is not None:
        operation["requestBody"] = path_spec.request_body

    if path_spec.response_override is not None:
        responses = dict(path_spec.response_override)
    else:
        responses = {}
        if path_spec.response_schema is not None:
            schema_name = _ensure_schema_component(
                spec, path_spec.response_schema, registered_schemas
            )
            responses["200"] = {
                "description": "Success",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                    }
                },
            }
        else:
            responses["200"] = {"description": "Success"}

    if path_spec.not_found:
        responses.setdefault("404", {"description": "Not found"})
    responses.update(path_spec.extra_responses)
    operation["responses"] = responses
    return operation


def generate_openapi_dict(app: Flask) -> Dict[str, Any]:
    """Build the OpenAPI document for the Flask app."""
    ma_plugin = MarshmallowPlugin()
    spec = APISpec(
        title="OpenCRE REST API",
        version="1.0.0",
        openapi_version="3.0.3",
        info={"description": API_DESCRIPTION},
        plugins=[ma_plugin],
    )

    with app.app_context():
        registered_schemas: Set[str] = set()
        for path_spec in OPENAPI_PATHS:
            operation = _operation_from_path(path_spec, spec, registered_schemas)
            spec.path(
                path=path_spec.path,
                operations={path_spec.method: operation},
            )

    spec_dict = spec.to_dict()
    spec_dict["paths"] = dict(sorted(spec_dict.get("paths", {}).items()))
    return spec_dict


def generate_openapi_yaml(app: Flask) -> str:
    return yaml.safe_dump(
        generate_openapi_dict(app),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def init_openapi(app: Flask) -> None:
    """Validate documented views exist on the Flask app (startup guard)."""
    view_names = {rule.endpoint.split(".")[-1] for rule in app.url_map.iter_rules()}
    missing = sorted(
        {p.view_name for p in OPENAPI_PATHS if p.view_name not in view_names}
    )
    if missing:
        raise RuntimeError(
            f"OpenAPI references unknown view functions: {', '.join(missing)}"
        )


def werkzeug_rule_to_openapi_path(rule: str) -> str:
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def is_rule_exempt(rule: str) -> bool:
    if rule in OPENAPI_GUARDRAIL_EXEMPT_RULES:
        return True
    return any(rule.startswith(prefix) for prefix in OPENAPI_GUARDRAIL_EXEMPT_PREFIXES)


def iter_in_scope_flask_rules(app: Flask) -> Iterable[Tuple[str, str]]:
    """Yield (method, openapi_path) for public GET /rest/v1 routes."""
    seen: Set[Tuple[str, str]] = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(OPENAPI_IN_SCOPE_PREFIX) and not is_rule_exempt(
            rule.rule
        ):
            openapi_path = werkzeug_rule_to_openapi_path(rule.rule)
            for method in rule.methods or set():
                if method.upper() == "GET":
                    key = ("GET", openapi_path)
                    if key not in seen:
                        seen.add(key)
                        yield "GET", openapi_path


def iter_spec_paths(spec_dict: Dict[str, Any]) -> Set[str]:
    return set(spec_dict.get("paths", {}).keys())


def normalize_yaml_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip() + "\n"
