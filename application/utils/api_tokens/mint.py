"""Mint and revoke JWT API tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import jwt

from application import sqla
from application.database import db
from application.utils.api_tokens.secret import ensure_api_token_jwt_secret

DEFAULT_EXPIRES_DAYS = 90
MAX_EXPIRES_DAYS = 365
_ALG = "HS256"


@dataclass(frozen=True)
class MintedToken:
    token: str
    jti: str
    name: str
    expires_at: datetime
    user_id: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def mint_api_token(
    *,
    user: db.User,
    name: str,
    expires_at: Optional[datetime] = None,
    expires_days: Optional[int] = None,
) -> MintedToken:
    """Create DB row + JWT. Caller must enforce admin allowlist."""
    label = (name or "").strip() or "api-key"
    if expires_at is None:
        days = expires_days if expires_days is not None else DEFAULT_EXPIRES_DAYS
        days = max(1, min(int(days), MAX_EXPIRES_DAYS))
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    if expires_at.tzinfo is not None:
        expires_at_naive = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        expires_at_naive = expires_at

    jti = db.generate_uuid()
    now = _utcnow()
    row = db.ApiKey(
        jti=jti,
        user_id=user.id,
        name=label,
        expires_at=expires_at_naive,
        revoked_at=None,
        created_at=now,
        last_used_at=None,
    )
    sqla.session.add(row)
    sqla.session.commit()

    secret = ensure_api_token_jwt_secret()
    token = jwt.encode(
        {
            "jti": jti,
            "sub": user.id,
            "email": user.email or "",
            "name": label,
            "iat": datetime.now(timezone.utc),
            "exp": (
                expires_at
                if expires_at.tzinfo
                else expires_at_naive.replace(tzinfo=timezone.utc)
            ),
        },
        secret,
        algorithm=_ALG,
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return MintedToken(
        token=token,
        jti=jti,
        name=label,
        expires_at=expires_at_naive,
        user_id=user.id,
    )


def revoke_api_token(jti: str, *, user_id: Optional[str] = None) -> bool:
    """Revoke a key; with ``user_id`` only that user's own key can be revoked."""
    q = sqla.session.query(db.ApiKey).filter(db.ApiKey.jti == jti)
    if user_id:
        q = q.filter(db.ApiKey.user_id == user_id)
    row = q.first()
    if row is None:
        return False
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        sqla.session.commit()
    return True


def list_api_tokens(*, user_id: Optional[str] = None) -> List[dict[str, Any]]:
    q = sqla.session.query(db.ApiKey).order_by(db.ApiKey.created_at.desc())
    if user_id:
        q = q.filter(db.ApiKey.user_id == user_id)
    out: List[dict[str, Any]] = []
    for row in q.all():
        out.append(
            {
                "jti": row.jti,
                "user_id": row.user_id,
                "name": row.name,
                "expires_at": (
                    row.expires_at.isoformat() + "Z" if row.expires_at else None
                ),
                "revoked_at": (
                    row.revoked_at.isoformat() + "Z" if row.revoked_at else None
                ),
                "created_at": (
                    row.created_at.isoformat() + "Z" if row.created_at else None
                ),
                "last_used_at": (
                    row.last_used_at.isoformat() + "Z" if row.last_used_at else None
                ),
            }
        )
    return out
