"""Human-facing commands for the MCP client: login, logout, status.

Owns all printing. Everything is written to stderr so stdout stays clean for
JSON-RPC when the stdio server runs.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import sys
from typing import List

from application.mcp import auth

COMMANDS = ("login", "logout", "status")


def _say(message: str = "") -> None:
    print(message, file=sys.stderr)


def _login() -> int:
    def show(url: str, code: str) -> None:
        _say(f"\n  Open: {url}\n  Code: {code}\n")
        _say("  Waiting for approval...")

    try:
        claims = auth.login(show)
    except auth.AuthError as exc:
        _say(f"Login failed: {exc}")
        return 1
    _say(f"Logged in as {claims.get('email') or claims.get('sub')}")
    return 0


def _logout() -> int:
    if auth.logout():
        _say("Logged out.")
    else:
        _say("No stored credential.")
    return 0


def _status() -> int:
    info = auth.status()
    if not info["logged_in"]:
        _say("Not logged in.")
        if info.get("error"):
            _say(f"  {info['error']}")
        return 1
    _say(f"Logged in as : {info.get('email')}")
    _say(f"Subject      : {info.get('sub')}")
    _say(f"Audience     : {info.get('audience')}")
    _say(f"Token expires: {info.get('expires_in')}s")
    return 0


def parse_and_run_command(command: List[str]) -> int:
    handlers = {"login": _login, "logout": _logout, "status": _status}
    if len(command) != 1 or command[0] not in handlers:
        _say(f"Usage: python -m application.mcp [{'|'.join(COMMANDS)}]")
        return 2
    return handlers[command[0]]()
