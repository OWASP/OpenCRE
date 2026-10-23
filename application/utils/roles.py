"""Who may do what: two roles shared by the web app and the MCP server.

``user``   any account on an allowed domain (``LOGIN_ALLOWED_DOMAINS``, e.g. ``owasp.org``) may
           use the chatbot, MCP ``ask`` and the read-only tools.
``admin``  the named accounts in ``ADMIN_EMAILS`` may also use the admin panel, manage every API
           key, and call admin-only MCP tools.

Roles are derived from the email on every request (never stored in a token), so removing someone
from ``ADMIN_EMAILS`` takes effect immediately.

Backward compatible: while ``ADMIN_EMAILS`` is unset the old behaviour stays — ``LOGIN_ALLOWED_EMAILS``
is the single allowlist and everyone on it is an admin; nobody else has any role.
"""

from __future__ import annotations

import os
from typing import Optional, Set

USER = "user"
ADMIN = "admin"
_RANK = {USER: 1, ADMIN: 2}


def _csv(name: str) -> Set[str]:
    return {
        e.strip().lower() for e in (os.environ.get(name) or "").split(",") if e.strip()
    }


def roles_enabled() -> bool:
    """True once ``ADMIN_EMAILS`` is set (the opt-in switch for the two-role model)."""
    return bool((os.environ.get("ADMIN_EMAILS") or "").strip())


def _is_production() -> bool:
    return (os.environ.get("FLASK_CONFIG") or "").strip().lower() == "production"


def admin_emails() -> Set[str]:
    return _csv("ADMIN_EMAILS") if roles_enabled() else _csv("LOGIN_ALLOWED_EMAILS")


def _domain_allowed(email: str) -> bool:
    domains = [
        d.strip().lower()
        for d in (os.environ.get("LOGIN_ALLOWED_DOMAINS") or "").split(",")
        if d.strip()
    ]
    if not domains:
        return False  # fail closed: a domain must be named explicitly
    if domains == ["*"]:
        return True
    host = email.rsplit("@", 1)[-1] if "@" in email else ""
    return any(
        host == d.lstrip("@") or host.endswith("." + d.lstrip("@")) for d in domains
    )


def role_for(email: Optional[str]) -> Optional[str]:
    """``admin``, ``user`` or ``None`` (no access) for this account."""
    addr = (email or "").strip().lower()
    if not roles_enabled():
        # Legacy single allowlist: on it = admin; an empty list allows anyone outside production
        # (even a session without an email, as before) and nobody in production.
        allow = admin_emails()
        if not allow:
            return None if _is_production() else ADMIN
        return ADMIN if addr in allow else None
    if not addr:
        return None
    if addr in admin_emails():
        return ADMIN
    return USER if _domain_allowed(addr) else None


def has_role(email: Optional[str], needed: str) -> bool:
    role = role_for(email)
    return role is not None and _RANK[role] >= _RANK[needed]
