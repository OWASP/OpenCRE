"""Entry point: python -m application.mcp [login|logout|status]"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import asyncio
import os
import pathlib
import sys


def _load_repo_env() -> None:
    """Fall back to the repo's .env for anything the MCP client did not set.

    MCP clients cannot set a working directory, so the path is resolved from
    this file rather than the cwd. Values already present in the environment
    win, keeping the client config authoritative.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def main() -> None:
    _load_repo_env()
    command = sys.argv[1:]
    if command:
        from application.mcp.cli import parse_and_run_command

        raise SystemExit(parse_and_run_command(command))

    logger.info("starting OpenCRE MCP stdio server")
    from application.mcp.server import run_stdio

    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
