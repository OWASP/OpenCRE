"""Helpers for handling database URLs in logs and reports."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "")


def assert_local_db_url(url: str) -> None:
    """Exit unless ``url`` is a local database (or a local file path).

    Guards scripts that delete or rewrite rows, so a stray ``DEV_DATABASE_URL``
    pointing at Heroku or another host can never be the target.
    """
    if not url or not url.strip():
        raise SystemExit("refusing empty database url")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise SystemExit("refusing unparseable database url")
    lowered = url.lower()
    if "heroku" in lowered or "opencreorg" in lowered:
        raise SystemExit(
            f"refusing production/Heroku URL (host {host!r}); use cre_prodclone locally"
        )
    if host not in _LOCAL_HOSTS:
        raise SystemExit(f"refusing non-local host {host!r}; this script is local-only")


def assert_local_clone_url(url: str) -> None:
    """Like :func:`assert_local_db_url`, and also refuse the database named ``cre``.

    For scripts that clear shared tables: they must run against a throwaway clone
    (for example ``cre_prodclone``), never the working database.
    """
    assert_local_db_url(url)
    db_name = (urlsplit(url).path or "").lstrip("/").split("/")[0]
    if db_name == "cre":
        raise SystemExit(
            "refusing database 'cre'; pass cre_prodclone "
            "(postgresql://cre:password@127.0.0.1:5432/cre_prodclone)"
        )


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
