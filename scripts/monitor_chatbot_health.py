#!/usr/bin/env python3
"""
Monitor production (or staging) chatbot health over HTTP.

Checks that the chatbot SPA shell loads and that the completion API is
reachable (unauthenticated callers must receive HTTP 401 — not 404/500/503).

Does not send authenticated chat prompts (avoids LLM cost and login secrets).

Exit codes:
  0 — all checks passed
  1 — one or more health checks failed
  2 — configuration or unexpected request failure
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


_DEFAULT_HEADERS = {
    "Accept": "*/*",
    "User-Agent": "OpenCRE-Chatbot-Monitor/1.0 (+https://opencre.org)",
}

# Webpack interop for a missing named `sanitize` export becomes `(0,e.sanitize)(...)`.
# Healthy builds call `DOMPurify.sanitize(...)` as a method (e.g. `Fw.sanitize(String(...))`).
_BROKEN_NAMED_SANITIZE_RE = re.compile(r"\(0,[A-Za-z_$][\w$]*\.sanitize\)\(")
_HEALTHY_SANITIZE_STRING_RE = re.compile(r"\.sanitize\(String\(")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "OPENCRE_CHATBOT_MONITOR_BASE_URL", "https://opencre.org"
        ),
        help="OpenCRE base URL (default: https://opencre.org)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("OPENCRE_CHATBOT_MONITOR_TIMEOUT", "30")),
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output JSON report path",
    )
    return parser.parse_args()


def _http_get(url: str, timeout: int) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = (exc.read() or b"").decode("utf-8", errors="replace")
        return int(exc.code), body


def _http_post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    headers = {
        **_DEFAULT_HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = (exc.read() or b"").decode("utf-8", errors="replace")
        return int(exc.code), body


def check_chatbot_page(base_url: str, timeout: int) -> dict[str, Any]:
    """GET /chatbot and confirm the SPA shell is served."""
    url = f"{base_url}/chatbot"
    try:
        status, body = _http_get(url, timeout)
    except Exception as exc:
        return {
            "name": "chatbot_page",
            "ok": False,
            "bucket": "request_exception",
            "error": str(exc),
        }

    if status != 200:
        return {
            "name": "chatbot_page",
            "ok": False,
            "bucket": f"http_{status}",
            "status_code": status,
        }

    body_l = body.lower()
    # SPA index.html references the webpack bundle; chatbot route is client-side.
    if "bundle.js" not in body_l:
        return {
            "name": "chatbot_page",
            "ok": False,
            "bucket": "missing_bundle_js",
            "status_code": status,
        }

    return {
        "name": "chatbot_page",
        "ok": True,
        "bucket": "ok",
        "status_code": status,
    }


def check_bundle_js(base_url: str, timeout: int) -> dict[str, Any]:
    """GET /bundle.js and confirm the frontend asset is present."""
    url = f"{base_url}/bundle.js"
    try:
        status, body = _http_get(url, timeout)
    except Exception as exc:
        return {
            "name": "bundle_js",
            "ok": False,
            "bucket": "request_exception",
            "error": str(exc),
        }

    if status != 200:
        return {
            "name": "bundle_js",
            "ok": False,
            "bucket": f"http_{status}",
            "status_code": status,
        }

    if len(body) < 1000:
        return {
            "name": "bundle_js",
            "ok": False,
            "bucket": "bundle_too_small",
            "status_code": status,
            "bytes": len(body),
        }

    return {
        "name": "bundle_js",
        **analyze_bundle_js(body),
        "status_code": status,
        "bytes": len(body),
    }


def analyze_bundle_js(body: str) -> dict[str, Any]:
    """Return ok/bucket fields for a downloaded (or fixture) bundle.js body."""
    if _BROKEN_NAMED_SANITIZE_RE.search(body):
        return {
            "ok": False,
            "bucket": "broken_named_sanitize_interop",
        }

    healthy_hits = len(_HEALTHY_SANITIZE_STRING_RE.findall(body))
    # Chatbot + MarkdownFromRepo both use DOMPurify.sanitize(String(...)).
    if healthy_hits < 2:
        return {
            "ok": False,
            "bucket": "missing_dompurify_sanitize_string",
            "healthy_sanitize_string_hits": healthy_hits,
        }

    return {
        "ok": True,
        "bucket": "ok",
        "healthy_sanitize_string_hits": healthy_hits,
    }


def check_completion_unauthenticated(base_url: str, timeout: int) -> dict[str, Any]:
    """POST /rest/v1/completion without session; expect 401 (endpoint alive)."""
    url = f"{base_url}/rest/v1/completion"
    try:
        status, body = _http_post_json(url, {"prompt": "healthcheck"}, timeout)
    except Exception as exc:
        return {
            "name": "completion_unauthenticated",
            "ok": False,
            "bucket": "request_exception",
            "error": str(exc),
        }

    if status == 401:
        return {
            "name": "completion_unauthenticated",
            "ok": True,
            "bucket": "ok_401",
            "status_code": status,
        }

    preview = body.strip().replace("\n", " ")[:200]
    return {
        "name": "completion_unauthenticated",
        "ok": False,
        "bucket": f"unexpected_http_{status}",
        "status_code": status,
        "body_preview": preview,
    }


def run_checks(base_url: str, timeout: int) -> list[dict[str, Any]]:
    base = base_url.rstrip("/")
    return [
        check_chatbot_page(base, timeout),
        check_bundle_js(base, timeout),
        check_completion_unauthenticated(base, timeout),
    ]


def main() -> int:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    timeout = args.timeout_seconds

    try:
        checks = run_checks(base_url, timeout)
    except Exception as exc:
        print(f"Chatbot health check failed unexpectedly: {exc}", file=sys.stderr)
        return 2

    failures = [c for c in checks if not c.get("ok")]
    report: dict[str, Any] = {
        "base_url": base_url,
        "checks": checks,
        "passed": len(checks) - len(failures),
        "failed": len(failures),
        "alert": len(failures) > 0,
    }

    print(
        f"Chatbot health check for {base_url}: "
        f"{report['passed']}/{len(checks)} passed, {report['failed']} failed"
    )
    for item in checks:
        status = "ok" if item.get("ok") else "FAIL"
        print(f"  - [{status}] {item['name']}: {item.get('bucket')}")

    if args.output_json:
        parent = os.path.dirname(args.output_json)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(f"Wrote report: {args.output_json}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
