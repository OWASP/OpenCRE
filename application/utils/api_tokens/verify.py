"""Verify Bearer/X-API-Key JWTs and bind identity on Flask ``g``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import jwt
from flask import g, request

from application import sqla
from application.database import db
from application.utils.api_tokens.secret import ensure_api_token_jwt_secret

_ALG = "HS256"


@dataclass(frozen=True)
class ApiKeyIdentity:
    jti: str
    user_id: str
    email: str


def extract_raw_token() -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if tok:
            return tok
    x = (request.headers.get("X-API-Key") or "").strip()
    return x or None


def api_key_allowed_for_request() -> bool:
    """True when this request may authenticate via API key.

    OIE/agent Admin REST allows Bearer for machine ops; other /admin HTML
    surfaces still require a Google session.
    """
    path = request.path or ""
    ops_prefixes = (
        "/admin/oie/",
        "/admin/ingest",
        "/admin/agent/",
        "/admin/config",
        "/admin/pipeline",
        "/admin/dashboard",
        "/admin/upstream-sync",
    )
    if path == "/admin/config" or any(path.startswith(p) for p in ops_prefixes):
        return True
    if path.startswith("/admin/") or path.startswith("/rest/v1/admin/"):
        return False
    if path.startswith("/rest/v1/api-keys"):
        return False
    if path.startswith("/rest/v1/user"):
        return True
    return request.method in ("POST", "PUT", "PATCH", "DELETE")


def verify_api_token(raw: str) -> Optional[ApiKeyIdentity]:
    """Validate JWT + DB row (expiry / revoke). Does not bind ``g``."""
    secret = ensure_api_token_jwt_secret()
    try:
        payload = jwt.decode(raw, secret, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    jti = str(payload.get("jti") or "").strip()
    user_id = str(payload.get("sub") or "").strip()
    email = str(payload.get("email") or "").strip()
    if not jti or not user_id:
        return None
    row = sqla.session.query(db.ApiKey).filter(db.ApiKey.jti == jti).first()
    if row is None or row.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row.expires_at and row.expires_at < now:
        return None
    if row.user_id != user_id:
        return None
    return ApiKeyIdentity(jti=jti, user_id=user_id, email=email or "")


def email_on_login_allowlist(email: Optional[str]) -> bool:
    """True when ``email`` is on LOGIN_ALLOWED_EMAILS.

    Mirrors Admin ``login_required`` / ``_login_email_allowed`` without Flask
    request path gates. Dev/test: empty allowlist allows anyone.
    ``FLASK_CONFIG=production``: empty allowlist fails closed.
    """
    raw = (os.environ.get("LOGIN_ALLOWED_EMAILS") or "").strip()
    is_prod = (os.environ.get("FLASK_CONFIG") or "").strip().lower() == "production"
    if not raw:
        return not is_prod
    allowed = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return (email or "").strip().lower() in allowed


def verify_admin_allowlisted_api_token(raw: str) -> Optional[ApiKeyIdentity]:
    """Path-agnostic Admin JWT check: signature + DB + LOGIN_ALLOWED_EMAILS."""
    identity = verify_api_token(raw)
    if identity is None:
        return None
    if not email_on_login_allowlist(identity.email):
        return None
    return identity


def bind_api_key_identity(identity: ApiKeyIdentity) -> None:
    g.api_key_jti = identity.jti
    g.api_key_user_id = identity.user_id
    g.api_key_email = identity.email
    row = sqla.session.query(db.ApiKey).filter(db.ApiKey.jti == identity.jti).first()
    if row is not None:
        row.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            sqla.session.commit()
        except Exception:
            sqla.session.rollback()


def try_authenticate_api_key() -> Optional[ApiKeyIdentity]:
    if not api_key_allowed_for_request():
        return None
    raw = extract_raw_token()
    if not raw:
        return None
    identity = verify_api_token(raw)
    if identity is None:
        return None
    bind_api_key_identity(identity)
    return identity
