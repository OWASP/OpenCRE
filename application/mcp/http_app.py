"""Streamable HTTP ASGI app for staging remote MCP (OPENCRE_MCP_REMOTE=1)."""

from __future__ import annotations

import os
from contextvars import Token
from typing import Callable, List, Optional, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from mcp.server.transport_security import TransportSecuritySettings

from application.mcp.remote_auth import authorization_header
from application.mcp.rest_client import RestClient
from application.mcp.server import build_server

DEFAULT_ALLOWED_HOSTS = (
    "staging.opencre.org",
    "staging.opencre.org:*",
    "127.0.0.1:*",
    "localhost:*",
)


def _truthy(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def parse_allowed_hosts(raw: Optional[str] = None) -> List[str]:
    value = raw if raw is not None else os.environ.get("OPENCRE_MCP_ALLOWED_HOSTS")
    if value is None or not str(value).strip():
        return list(DEFAULT_ALLOWED_HOSTS)
    hosts = [h.strip() for h in str(value).split(",") if h.strip()]
    return hosts or list(DEFAULT_ALLOWED_HOSTS)


def transport_security_settings(
    allowed_hosts: Optional[Sequence[str]] = None,
) -> TransportSecuritySettings:
    hosts = list(allowed_hosts) if allowed_hosts is not None else parse_allowed_hosts()
    origins: List[str] = []
    for host in hosts:
        base = host.split(":")[0] if ":" in host and not host.startswith("[") else host
        if base.endswith(":*"):
            base = base[:-2]
        if host.endswith(":*"):
            origins.append(f"https://{base}:*")
            origins.append(f"http://{base}:*")
        else:
            origins.append(f"https://{host}")
            origins.append(f"http://{host}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


class AuthorizationContextMiddleware(BaseHTTPMiddleware):
    """Store Authorization on a contextvar for remote ask gating."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        token: Token = authorization_header.set(request.headers.get("authorization"))
        try:
            return await call_next(request)
        finally:
            authorization_header.reset(token)


def create_http_app(
    *,
    rest_client: Optional[RestClient] = None,
    allowed_hosts: Optional[Sequence[str]] = None,
) -> ASGIApp:
    """Build Starlette ASGI app with Streamable HTTP at ``/mcp``."""
    if not _truthy(os.environ.get("OPENCRE_MCP_REMOTE")):
        raise RuntimeError(
            "Refusing to create remote MCP HTTP app without OPENCRE_MCP_REMOTE=1"
        )
    server = build_server(rest_client=rest_client)
    security = transport_security_settings(allowed_hosts=allowed_hosts)
    # Pass an explicit non-localhost host so SDK does not override our allowlist
    # with localhost-only defaults.
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=security,
        host="0.0.0.0",
        json_response=True,
        # One uvicorn worker / sessionful clients: stateful sessions for v1.
        stateless_http=False,
    )
    app.add_middleware(AuthorizationContextMiddleware)
    return app
