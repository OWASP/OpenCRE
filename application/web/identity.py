"""Who is making this request, and through which door.

A request authenticates either with the browser session cookie or with a
Google ID token issued to one of OpenCRE's registered clients. Both resolve to
the same ``users`` row; the channel decides how much that user may do here.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import re
from functools import wraps
from typing import Any, Dict, Optional, Tuple

from flask import abort, g, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from application.database import db

CHANNEL_WEB = "web"
CHANNEL_MCP = "mcp"

SCOPE_MYOPENCRE_READ = "myopencre:read"
SCOPE_MYOPENCRE_WRITE = "myopencre:write"

# A browser session is the user acting directly, so it carries every scope.
ALL_SCOPES: Tuple[str, ...] = (SCOPE_MYOPENCRE_READ, SCOPE_MYOPENCRE_WRITE)

# Granted the first time a user's MCP client calls, so logging in is enough to
# read. Writing stays an explicit choice, and a revoked scope is never restored.
DEFAULT_MCP_SCOPES: Tuple[str, ...] = (SCOPE_MYOPENCRE_READ,)

_BEARER_RE = re.compile(r"^Bearer\s+(\S+)$", re.IGNORECASE)
_IDENTITY_KEY = "cre_identity"


def allowed_audiences() -> Dict[str, str]:
    """Map each registered Google client id to the channel it represents."""
    audiences: Dict[str, str] = {}
    web = os.environ.get("GOOGLE_CLIENT_ID")
    mcp = os.environ.get("GOOGLE_MCP_CLIENT_ID")
    if web:
        audiences[web] = CHANNEL_WEB
    if mcp:
        audiences[mcp] = CHANNEL_MCP
    return audiences


def verify_google_token(token: str) -> Dict[str, Any]:
    """Verify signature, issuer and expiry. The seam tests patch."""
    return google_id_token.verify_oauth2_token(
        token, google_requests.Request(), audience=None
    )


def bearer_token() -> Optional[str]:
    match = _BEARER_RE.match(request.headers.get("Authorization", ""))
    return match.group(1) if match else None


def _identity_from_token(database: Any) -> Optional[Tuple[Any, str]]:
    token = bearer_token()
    if not token:
        return None
    try:
        claims = verify_google_token(token)
    except ValueError:
        logger.info("rejected a bearer token that failed verification")
        return None

    channel = allowed_audiences().get(claims.get("aud", ""))
    if channel is None:
        logger.info("rejected a bearer token issued for another audience")
        return None

    subject = claims.get("sub")
    if not subject:
        return None
    user = database.get_user_by_sub(subject)
    if user is None:
        return None
    if channel == CHANNEL_MCP:
        database.bootstrap_mcp_grants(user.id, list(DEFAULT_MCP_SCOPES))
    return user, channel


def _identity_from_session(database: Any) -> Optional[Tuple[Any, str]]:
    """A browser session is authenticated by ``session['user_id']`` alone.

    That is the pre-#1003 predicate and must not change: a session carrying only
    ``google_id`` stays anonymous, and a session whose row is missing is still a
    session (the view decides what to do about the absent user).
    """
    from flask import session

    if "user_id" not in session:
        return None
    from application.web.web_main import _resolve_current_user

    return _resolve_current_user(database), CHANNEL_WEB


def current_identity() -> Optional[Tuple[Any, str]]:
    """``(User, channel)`` for this request, or None. Cached per request."""
    if _IDENTITY_KEY not in g:
        database = db.Node_collection()
        identity = _identity_from_session(database)
        if identity is None:
            identity = _identity_from_token(database)
        setattr(g, _IDENTITY_KEY, identity)
    return getattr(g, _IDENTITY_KEY)


def current_user() -> Optional[Any]:
    identity = current_identity()
    return identity[0] if identity else None


def current_channel() -> Optional[str]:
    identity = current_identity()
    return identity[1] if identity else None


def is_session_authenticated() -> bool:
    """True only for a browser session, never for a token."""
    from flask import session

    return "user_id" in session


def current_scopes() -> Tuple[str, ...]:
    """What this caller may do. Google never carries OpenCRE scopes, so for
    the MCP channel they come from the ``mcp_grants`` table."""
    identity = current_identity()
    if identity is None:
        return ()
    user, channel = identity
    if channel == CHANNEL_WEB:
        return ALL_SCOPES
    return tuple(db.Node_collection().get_mcp_grants(user.id))


def require_scopes(*needed: str) -> Any:
    """Deny a caller whose channel does not carry every required scope."""

    def decorator(view: Any) -> Any:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if os.environ.get("NO_LOGIN") == "1":
                return view(*args, **kwargs)
            held = set(current_scopes())
            missing = [scope for scope in needed if scope not in held]
            if missing:
                abort(403, description=f"Missing scope(s): {', '.join(missing)}")
            return view(*args, **kwargs)

        return wrapper

    return decorator


def session_only(view: Any) -> Any:
    """Restrict a view to browser sessions so a token cannot widen its own
    grants."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if os.environ.get("NO_LOGIN") == "1":
            return view(*args, **kwargs)
        if not is_session_authenticated():
            abort(403, description="This endpoint requires a browser session")
        return view(*args, **kwargs)

    return wrapper
