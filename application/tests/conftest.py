"""Shared pytest setup for the OpenCRE test suite.

``application.feature_flags`` calls ``load_dotenv()`` at import, so a
contributor's local ``.env`` lands in ``os.environ`` for the whole test run.
Values that change what the code under test does must not leak in that way:
they make results depend on whose machine the suite runs on, and a stray
``NO_LOGIN`` would make every authorization test pass without testing anything.
"""

from __future__ import annotations

import os

import pytest

# Cleared before every test. Any test that needs one sets it explicitly.
AMBIENT_ENV_VARS = (
    "NO_LOGIN",
    "NO_LOAD_GRAPH_DB",
    "INSECURE_REQUESTS",
    "CRE_ENABLE_LOGIN",
    "CRE_ENABLE_MYOPENCRE",
    "OPENCRE_MCP_AUTH_TOOLS",
    "OPENCRE_MCP_TOKEN_FILE",
    "OPENCRE_BASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_MCP_CLIENT_ID",
    "GOOGLE_MCP_CLIENT_SECRET",
)


@pytest.fixture(autouse=True)
def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in AMBIENT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
