"""Entry point: python -m application.mcp"""

from __future__ import annotations

import asyncio
import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    from application.mcp.server import run_stdio

    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
