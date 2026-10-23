"""Admin JWT auth for remote MCP ``ask`` (staging Streamable HTTP only)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from application.utils.api_tokens.verify import (
    ApiKeyIdentity,
    bind_api_key_identity,
    verify_admin_allowlisted_api_token,
)

REMOTE_FLAG = "OPENCRE_MCP_REMOTE"

# Set by HTTP middleware for the current request; unset on stdio.
authorization_header: ContextVar[Optional[str]] = ContextVar(
    "opencre_mcp_authorization", default=None
)


class RemoteAskAuthError(Exception):
    """Remote ``ask`` refused; ``status`` is 401 or 403 for the tool error text."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"{status} {message}")


def remote_mode_enabled() -> bool:
    import os

    return (os.environ.get(REMOTE_FLAG) or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def extract_bearer(authorization: Optional[str] = None) -> Optional[str]:
    raw = authorization if authorization is not None else authorization_header.get()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        tok = raw[7:].strip()
        return tok or None
    return None


# Minimum role per MCP tool. Everything we ship today is read-only or answers questions, so any
# account with a role may call it. Tools that change state or expose operations go in
# ADMIN_ONLY_TOOLS (named admins only). Unknown tool names default to admin: deny by default.
ADMIN_ONLY_TOOLS: frozenset = frozenset()
USER_TOOL_PREFIXES = ("owasp_meta_",)
USER_TOOLS = frozenset({"ask", "rate_answer"})


def min_role_for_tool(tool_name: str, public_cre_tools=frozenset()) -> Optional[str]:
    """Role a tool needs; ``None`` for the public, read-only CRE REST tools (as before)."""
    from application.utils import roles

    if tool_name in ADMIN_ONLY_TOOLS:
        return roles.ADMIN
    if tool_name in USER_TOOLS or tool_name.startswith(USER_TOOL_PREFIXES):
        return roles.USER
    if tool_name in public_cre_tools:
        return None
    return roles.ADMIN


def require_remote_auth(
    tool_name: str, public_cre_tools=frozenset()
) -> Optional[ApiKeyIdentity]:
    """Verify the Bearer API key and that its owner holds the role ``tool_name`` needs.

    Returns ``None`` for the public CRE read tools (no key needed).
    """
    from application.utils import roles
    from application.utils.api_tokens.verify import (
        verify_api_token,
        verify_token_with_role,
    )

    needed = min_role_for_tool(tool_name, public_cre_tools)
    if needed is None:
        return None
    bearer = extract_bearer()
    if not bearer:
        raise RemoteAskAuthError(
            401, "Unauthorized: Bearer API key required (sign in and create one)."
        )
    identity = verify_token_with_role(bearer, needed)
    if identity is None:
        base = verify_api_token(bearer)
        if base is None:
            raise RemoteAskAuthError(
                401, "Unauthorized: invalid, expired, or revoked API key."
            )
        if roles.role_for(base.email) is None:
            raise RemoteAskAuthError(
                403, "Forbidden: this account has no access to this environment."
            )
        raise RemoteAskAuthError(
            403, f"Forbidden: the {needed} role is required for the tool '{tool_name}'."
        )
    try:
        bind_api_key_identity(identity)
    except Exception:
        # Binding last_used_at is best-effort; auth already succeeded.
        pass
    return identity


def require_remote_ask_auth() -> ApiKeyIdentity:
    """Back-compat name: the ``ask`` tool needs the user role."""
    return require_remote_auth("ask")
