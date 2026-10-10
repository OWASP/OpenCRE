"""Google device-flow credentials for the MCP client.

The only module that knows Google exists. Callers ask for an id_token and get
one, refreshed silently when needed. Never writes to stdout: that stream
carries JSON-RPC when the stdio server is running.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import base64
import json
import os
import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from application.mcp import token_store

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# Device flow supports only this set, and staying inside it keeps refresh
# tokens exempt from the 7-day expiry Google applies to Testing-mode apps.
SCOPES = "openid email profile"

REQUEST_TIMEOUT_SECONDS = 30.0
EXPIRY_SKEW_SECONDS = 60

_cached_id_token: Optional[str] = None


class AuthError(Exception):
    """Base error for MCP credential failures."""


class NotAuthenticated(AuthError):
    """No usable credential. The caller should run the login command."""


def _client_credentials() -> Tuple[str, str]:
    """Read client config lazily so importing this module never fails."""
    client_id = os.environ.get("GOOGLE_MCP_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_MCP_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise AuthError("GOOGLE_MCP_CLIENT_ID / GOOGLE_MCP_CLIENT_SECRET are not set.")
    return client_id, client_secret


def _decode_claims(id_token: str) -> Dict[str, Any]:
    """Read claims without verifying. Display only; REST verifies signatures."""
    try:
        payload = id_token.split(".")[1]
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        return json.loads(raw)
    except (IndexError, ValueError):
        return {}


def _is_fresh(id_token: str) -> bool:
    exp = _decode_claims(id_token).get("exp")
    if not isinstance(exp, (int, float)):
        return False
    return time.time() < exp - EXPIRY_SKEW_SECONDS


def _refresh(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Trade a refresh token for fresh tokens. None if it is no longer valid."""
    client_id, client_secret = _client_credentials()
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 200:
        return response.json()
    logger.info("refresh token rejected with status %s", response.status_code)
    return None


def login(on_code: Callable[[str, str], None]) -> Dict[str, Any]:
    """Run the device flow. `on_code(verification_url, user_code)` displays the
    prompt before polling begins. Returns the id_token claims on success."""
    client_id, client_secret = _client_credentials()

    response = requests.post(
        DEVICE_CODE_URL,
        data={"client_id": client_id, "scope": SCOPES},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise AuthError(f"device/code failed [{response.status_code}]: {response.text}")
    device = response.json()

    # Google spells it verification_url; RFC 8628 says verification_uri.
    url = device.get("verification_url") or device.get("verification_uri")
    on_code(url, device["user_code"])

    interval = device.get("interval", 5)
    deadline = time.time() + device["expires_in"]
    while time.time() < deadline:
        time.sleep(interval)
        polled = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device["device_code"],
                "grant_type": DEVICE_GRANT,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        body = polled.json()
        if polled.status_code == 200:
            return _store(body)
        error = body.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise AuthError(f"authorization failed: {error or body}")
    raise AuthError("timed out: the code expired before it was approved")


def _store(tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Persist the refresh token and cache the id_token. Returns its claims."""
    global _cached_id_token

    # A refresh response omits refresh_token; keep the one already held.
    refresh_token = tokens.get("refresh_token") or token_store.load()
    if refresh_token:
        token_store.save(refresh_token)

    _cached_id_token = tokens.get("id_token")
    return _decode_claims(_cached_id_token) if _cached_id_token else {}


def current_id_token() -> str:
    """A valid id_token, refreshing if needed."""
    global _cached_id_token

    if _cached_id_token and _is_fresh(_cached_id_token):
        return _cached_id_token

    refresh_token = token_store.load()
    if not refresh_token:
        raise NotAuthenticated("Not logged in. Run: python -m application.mcp login")

    tokens = _refresh(refresh_token)
    if tokens is None:
        _cached_id_token = None
        raise NotAuthenticated(
            "Stored credential is no longer valid. "
            "Run: python -m application.mcp login"
        )
    _store(tokens)
    if not _cached_id_token:
        raise AuthError("token endpoint returned no id_token")
    return _cached_id_token


def logout() -> bool:
    global _cached_id_token

    _cached_id_token = None
    return token_store.clear()


def status() -> Dict[str, Any]:
    """Describe the stored credential without raising when absent."""
    client_id = os.environ.get("GOOGLE_MCP_CLIENT_ID")
    if not token_store.load():
        return {"logged_in": False, "client_id": client_id}
    try:
        claims = _decode_claims(current_id_token())
    except AuthError as exc:
        return {"logged_in": False, "client_id": client_id, "error": str(exc)}
    return {
        "logged_in": True,
        "client_id": client_id,
        "email": claims.get("email"),
        "sub": claims.get("sub"),
        "audience": claims.get("aud"),
        "expires_in": int(claims.get("exp", 0) - time.time()),
    }
