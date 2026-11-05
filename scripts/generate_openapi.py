#!/usr/bin/env python3
"""Generate docs/api/openapi.yaml from the Flask app OpenAPI registry."""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from application import create_app  # noqa: E402
from application.web.openapi_registry import (  # noqa: E402
    generate_openapi_yaml,
    normalize_yaml_text,
)

OUTPUT_PATH = os.path.join(REPO_ROOT, "docs", "api", "openapi.yaml")


def main() -> int:
    os.environ.setdefault("FLASK_CONFIG", "testing")
    os.environ.setdefault("NO_LOGIN", "1")
    app = create_app(mode="test")
    yaml_text = normalize_yaml_text(generate_openapi_yaml(app))
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
