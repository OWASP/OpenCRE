"""Entry point: python -m application.mcp"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import asyncio


def main() -> None:
    logger.info("starting OpenCRE MCP stdio server")
    from application.mcp.server import run_stdio

    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
