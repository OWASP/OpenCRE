"""HTTP adapter from MCP tools to the OpenCRE public REST API.

REST remains the execution and security boundary. Callers cannot choose the
base URL, HTTP method, or arbitrary paths.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Set
from urllib.parse import quote, urljoin

import requests
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from application.defs import cre_defs as defs
from application.mcp.catalog import ToolSpec, get_tool
from application.mcp.openapi_loader import operation_input_schema

DEFAULT_BASE_URL = "http://127.0.0.1:5000"
DEFAULT_TIMEOUT_SECONDS = 30.0

# Path params must be single URL segments — no separators that alter routing.
_UNSAFE_PATH_PARAM = re.compile(r"[/?#]")

# First-path segments under /rest/v1 that are static routes, not Credoctypes.
# Blocked so get_node cannot collide with MyOpenCRE / auth / other surfaces.
_RESERVED_NTYPES: Set[str] = {
    "user",
    "id",
    "name",
    "tags",
    "standards",
    "ga_standards",
    "text_search",
    "root_cres",
    "all_cres",
    "map_analysis",
    "map_analysis_weak_links",
    "ma_job_results",
    "health",
    "config",
    "completion",
    "login",
    "logout",
    "callback",
    "cre_csv",
    "cre_csv_import",
    "openapi.yaml",
    "deeplink",
}


class RestClientError(Exception):
    """Base error for MCP REST adapter failures."""


class RestRequestError(RestClientError):
    """Invalid tool arguments or unsafe path construction."""


class RestResponseError(RestClientError):
    """Non-success HTTP response from OpenCRE REST."""

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class RestResult:
    status_code: int
    data: Any
    text: str


def normalize_base_url(base_url: Optional[str] = None) -> str:
    raw = (
        base_url if base_url is not None else os.environ.get("OPENCRE_BASE_URL")
    ) or (DEFAULT_BASE_URL)
    return raw.rstrip("/")


def _new_session() -> requests.Session:
    """Session that never keeps cookies or env/netrc credentials (v1 public only)."""
    session = requests.Session()
    # Disable Requests env/netrc credential pickup (trust_env defaults to True).
    session.trust_env = False
    session.cookies.clear()
    return session


class RestClient:
    """Execute allowlisted GET templates against OPENCRE_BASE_URL."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        session: Optional[Any] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        # base_url is constructor/env only — never a tool argument.
        self._base_url = normalize_base_url(base_url)
        self._session = session if session is not None else _new_session()
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def call_tool(
        self, tool_name: str, arguments: Optional[Mapping[str, Any]] = None
    ) -> RestResult:
        try:
            tool = get_tool(tool_name)
        except KeyError as exc:
            raise RestRequestError(str(exc)) from exc
        return self.call_spec(tool, arguments or {})

    def call_spec(self, tool: ToolSpec, arguments: Mapping[str, Any]) -> RestResult:
        if tool.method.upper() != "GET":
            raise RestRequestError(f"Only GET is supported (got {tool.method})")

        schema = operation_input_schema(tool)
        path_param_names = _path_param_names(tool.path_template)
        allowed = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])

        args = dict(arguments)
        unknown = sorted(set(args) - allowed)
        if unknown:
            raise RestRequestError(
                f"Unexpected argument(s) for {tool.name}: {', '.join(unknown)}"
            )
        missing = sorted(required - set(args))
        if missing:
            raise RestRequestError(
                f"Missing required argument(s) for {tool.name}: {', '.join(missing)}"
            )
        # Enforce the exact OpenAPI-derived JSON Schema (types, enums, etc.).
        _validate_against_input_schema(tool.name, schema, args)

        path_params: Dict[str, str] = {}
        query_params: Dict[str, Any] = {}
        for key, value in args.items():
            if key in path_param_names:
                path_params[key] = _sanitize_path_value(key, value)
            else:
                query_params[key] = value

        missing_path = sorted(set(path_param_names) - set(path_params))
        if missing_path:
            raise RestRequestError(
                f"Missing path parameter(s) for {tool.name}: {', '.join(missing_path)}"
            )

        _validate_node_type_param(path_params)
        path = _render_path(tool.path_template, path_params)
        url = urljoin(self._base_url + "/", path.lstrip("/"))
        response = self._session.get(
            url,
            params=_encode_query(query_params),
            timeout=self._timeout,
            allow_redirects=False,
        )
        # Never retain cookies across tool calls (no credential forwarding).
        if hasattr(self._session, "cookies"):
            try:
                self._session.cookies.clear()
            except Exception:
                pass
        return _parse_response(response)


def flask_test_session(flask_client: Any) -> "_FlaskTestSession":
    """Adapt Flask's test_client to the requests Session.get interface."""
    return _FlaskTestSession(flask_client)


class _FlaskTestResponse:
    def __init__(self, response: Any) -> None:
        self.status_code = int(response.status_code)
        raw = response.get_data(as_text=True)
        self.text = (
            raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        )
        self.headers = getattr(response, "headers", {})

    def json(self) -> Any:
        return json.loads(self.text)


class _FlaskTestSession:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(
        self,
        url: str,
        params: Optional[Any] = None,
        timeout: Optional[float] = None,
        allow_redirects: bool = False,
        **_kwargs: Any,
    ) -> _FlaskTestResponse:
        del timeout, allow_redirects  # parity with requests; unused by test client
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path or "/"
        response = self._client.get(path, query_string=params)
        return _FlaskTestResponse(response)


def _validate_against_input_schema(
    tool_name: str, schema: Mapping[str, Any], arguments: Mapping[str, Any]
) -> None:
    """Validate tool args with Draft7Validator (OpenAPI 3.0.3 JSON Schema subset)."""
    try:
        Draft7Validator(schema).validate(arguments)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        detail = f"{path}: {exc.message}" if path else exc.message
        raise RestRequestError(f"Invalid arguments for {tool_name}: {detail}") from exc


def _path_param_names(template: str) -> Sequence[str]:
    return re.findall(r"\{([^}]+)\}", template)


def _sanitize_path_value(name: str, value: Any) -> str:
    if value is None or isinstance(value, (dict, list, bool)):
        raise RestRequestError(f"Invalid path parameter '{name}'")
    text = str(value).strip()
    if not text:
        raise RestRequestError(f"Path parameter '{name}' must be non-empty")
    if _UNSAFE_PATH_PARAM.search(text) or ".." in text or text.startswith("//"):
        raise RestRequestError(f"Path parameter '{name}' contains unsafe characters")
    return text


def _validate_node_type_param(path_params: Mapping[str, str]) -> None:
    """Prevent get_node path collisions with static /rest/v1 routes (e.g. user/resources)."""
    if "ntype" not in path_params:
        return
    ntype = path_params["ntype"]
    lowered = ntype.lower()
    if lowered in _RESERVED_NTYPES:
        raise RestRequestError(
            f"Path parameter 'ntype' value '{ntype}' is reserved and not a node type"
        )
    allowed = {t.value.lower() for t in defs.Credoctypes}
    # Match Flask find_node_by_name: case-insensitive Credoctypes only.
    if lowered not in allowed:
        raise RestRequestError(
            f"Path parameter 'ntype' must be one of: "
            f"{', '.join(sorted(t.value for t in defs.Credoctypes))}"
        )


def _render_path(template: str, path_params: Mapping[str, str]) -> str:
    path = template
    for name, value in path_params.items():
        token = "{" + name + "}"
        if token not in path:
            raise RestRequestError(f"Unknown path parameter '{name}' for template")
        path = path.replace(token, quote(value, safe=""))
    if "{" in path or "}" in path:
        raise RestRequestError("Unresolved path parameters in template")
    if ".." in path.split("/"):
        raise RestRequestError("Refusing path traversal in rendered route")
    return path


def _encode_query(query_params: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """Preserve list query params for Flask's getlist / OpenAPI explode style."""
    encoded: Dict[str, Any] = {}
    for key, value in query_params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            encoded[key] = [str(item) for item in value]
        elif isinstance(value, bool):
            encoded[key] = "true" if value else "false"
        else:
            encoded[key] = value
    return encoded


def _parse_response(response: Any) -> RestResult:
    status = int(getattr(response, "status_code", 0))
    text = getattr(response, "text", "") or ""
    data: Any
    try:
        data = response.json()
    except Exception:
        data = text

    if status < 200 or status >= 300:
        if isinstance(data, dict):
            message = (
                data.get("message")
                or data.get("error")
                or data.get("description")
                or text
                or f"HTTP {status}"
            )
        else:
            message = text or f"HTTP {status}"
        raise RestResponseError(status, f"REST {status}: {message}", body=data)

    return RestResult(status_code=status, data=data, text=text)
