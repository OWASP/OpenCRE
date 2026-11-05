#!/usr/bin/env python3
"""Deterministic OpenAPI guardrail: route coverage, spec freshness, validity."""

from __future__ import annotations

import os
import sys
from typing import Set, Tuple

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from openapi_spec_validator import validate  # noqa: E402

from application import create_app  # noqa: E402
from application.web.openapi_registry import (  # noqa: E402
    OPENAPI_DOCUMENTED_VIEW_NAMES,
    OPENAPI_PATHS,
    generate_openapi_yaml,
    iter_in_scope_flask_rules,
    iter_spec_paths,
    normalize_yaml_text,
)

COMMITTED_SPEC = os.path.join(REPO_ROOT, "docs", "api", "openapi.yaml")


def _expected_view_names() -> Set[str]:
    return {p.view_name for p in OPENAPI_PATHS}


def _check_documented_views() -> Tuple[bool, str]:
    expected = _expected_view_names()
    missing = sorted(expected - OPENAPI_DOCUMENTED_VIEW_NAMES)
    if missing:
        return (
            False,
            f"undocumented view functions (missing @openapi_documented): {', '.join(missing)}",
        )
    return True, "documented views OK"


def _check_route_coverage(app, spec_dict) -> Tuple[bool, str]:
    flask_rules = set(iter_in_scope_flask_rules(app))
    spec_paths = iter_spec_paths(spec_dict)
    missing_in_spec = sorted(
        {path for _method, path in flask_rules if path not in spec_paths}
    )
    if missing_in_spec:
        return (
            False,
            f"Flask routes missing from OpenAPI spec: {', '.join(missing_in_spec)}",
        )
    return True, "route coverage OK"


def _check_freshness(app) -> Tuple[bool, str]:
    if not os.path.isfile(COMMITTED_SPEC):
        return False, f"missing committed spec: {COMMITTED_SPEC}"
    generated = normalize_yaml_text(generate_openapi_yaml(app))
    with open(COMMITTED_SPEC, "r", encoding="utf-8") as f:
        committed = normalize_yaml_text(f.read())
    if generated != committed:
        return False, "docs/api/openapi.yaml is stale (run: make openapi-generate)"
    return True, "spec freshness OK"


def _check_validity(spec_dict) -> Tuple[bool, str]:
    try:
        validate(spec_dict)
    except Exception as exc:
        return False, f"OpenAPI spec validation failed: {exc}"
    return True, "spec validity OK"


def main() -> int:
    os.environ.setdefault("FLASK_CONFIG", "testing")
    os.environ.setdefault("NO_LOGIN", "1")
    app = create_app(mode="test")

    checks = [
        _check_documented_views(),
        _check_freshness(app),
    ]
    if os.path.isfile(COMMITTED_SPEC):
        with open(COMMITTED_SPEC, "r", encoding="utf-8") as f:
            spec_dict = yaml.safe_load(f)
        checks.append(_check_validity(spec_dict))
        checks.append(_check_route_coverage(app, spec_dict))

    failures = [msg for ok, msg in checks if not ok]
    if failures:
        print("OPENAPI_GUARDRAIL_FAIL:")
        for msg in failures:
            print(f"  - {msg}")
        return 2

    print("OPENAPI_GUARDRAIL_OK:")
    for _ok, msg in checks:
        print(f"  - {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
