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


def require_remote_ask_auth() -> ApiKeyIdentity:
    """Verify Bearer Admin JWT + allowlist. Raises RemoteAskAuthError on failure."""
    bearer = extract_bearer()
    if not bearer:
        raise RemoteAskAuthError(
            401,
            "Unauthorized: Bearer Admin API token required for remote ask.",
        )
    identity = verify_admin_allowlisted_api_token(bearer)
    if identity is None:
        # Distinguish invalid/revoked vs allowlist via a second cheap check.
        from application.utils.api_tokens.verify import (
            email_on_login_allowlist,
            verify_api_token,
        )

        base = verify_api_token(bearer)
        if base is None:
            raise RemoteAskAuthError(
                401,
                "Unauthorized: invalid, expired, or revoked API token.",
            )
        if not email_on_login_allowlist(base.email):
            raise RemoteAskAuthError(
                403,
                "Forbidden: API key owner is not on the allowlist for this environment.",
            )
        raise RemoteAskAuthError(401, "Unauthorized: invalid API token.")
    try:
        bind_api_key_identity(identity)
    except Exception:
        # Binding last_used_at is best-effort; auth already succeeded.
        pass
    return identity
