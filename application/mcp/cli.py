"""Human-facing commands for the MCP client: login, logout, status, serve-http.

Owns all printing. Everything is written to stderr so stdout stays clean for
JSON-RPC when the stdio server runs.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import sys
from typing import List

from application.mcp import auth

COMMANDS = ("login", "logout", "status", "serve-http")


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


def _serve_http() -> int:
    """Run Streamable HTTP MCP (staging only; requires OPENCRE_MCP_REMOTE=1)."""
    from application.mcp.remote_auth import REMOTE_FLAG, remote_mode_enabled

    if not remote_mode_enabled():
        _say(
            f"Refusing to start HTTP MCP without {REMOTE_FLAG}=1 "
            "(staging-only remote transport)."
        )
        return 1

    import uvicorn

    from application import create_app
    from application.mcp.http_app import create_http_app

    host = (os.environ.get("OPENCRE_MCP_HTTP_HOST") or "127.0.0.1").strip()
    port_raw = (os.environ.get("OPENCRE_MCP_HTTP_PORT") or "5002").strip()
    try:
        port = int(port_raw)
    except ValueError:
        _say(f"Invalid OPENCRE_MCP_HTTP_PORT: {port_raw}")
        return 2

    mode = (os.environ.get("FLASK_CONFIG") or "production").strip() or "production"
    flask_app = create_app(mode="test" if mode == "test" else mode)
    # Flask app context for JWT DB checks and ask/meta for the process lifetime.
    ctx = flask_app.app_context()
    ctx.push()
    try:
        asgi = create_http_app()
        import threading

        from application.utils.comprehension.shared import warm_up

        def _warm() -> None:
            with flask_app.app_context():
                warm_up()

        threading.Thread(target=_warm, name="opencre-warmup", daemon=True).start()
        _say(f"OpenCRE remote MCP (Streamable HTTP) on http://{host}:{port}/mcp")
        # One worker: sessionful Streamable HTTP clients (sticky if scaled later).
        uvicorn.run(asgi, host=host, port=port, workers=1, log_level="info")
    except Exception as exc:
        _say(f"HTTP MCP failed to start: {exc}")
        return 1
    finally:
        ctx.pop()
    return 0


def parse_and_run_command(command: List[str]) -> int:
    handlers = {
        "login": _login,
        "logout": _logout,
        "status": _status,
        "serve-http": _serve_http,
    }
    if len(command) != 1 or command[0] not in handlers:
        _say(f"Usage: python -m application.mcp [{'|'.join(COMMANDS)}]")
        return 2
    return handlers[command[0]]()
