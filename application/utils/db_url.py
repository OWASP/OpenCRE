"""Helpers for handling database URLs in logs and reports."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_db_url(url: str) -> str:
    """Replace the password in ``scheme://user:password@host/db`` with ``***``.

    Anything that is not a URL with credentials (file paths, bare names) is
    returned unchanged.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable database url>"
    userinfo, sep, hostport = parts.netloc.rpartition("@")
    if not sep or ":" not in userinfo:
        return url
    user = userinfo.split(":", 1)[0]
    return urlunsplit(parts._replace(netloc=f"{user}:***@{hostport}"))
