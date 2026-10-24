#!/usr/bin/env python3
"""Black-box health check of a public OpenCRE deployment (HTTP only, stdlib only).

    python scripts/ops/health_check.py --env production            # https://opencre.org
    python scripts/ops/health_check.py --env staging               # https://staging.opencre.org
    python scripts/ops/health_check.py --base-url https://example.org --notify

Checks (read-only GETs): the home page answers, the REST API returns real data, and answers come fast
enough. Exit 0 = healthy, 1 = at least one check failed. With --notify a failure is sent to
ALERT_WEBHOOK_URL / NTFY_URL when those are set (see scripts/ops/notify.py). Production gap analysis is
never computed here: only cached endpoints are read (AGENTS.md rule).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Tuple

ENVIRONMENTS = {
    "production": "https://opencre.org",
    "staging": "https://staging.opencre.org",
}
SLOW_SECONDS = 5.0

Fetch = Callable[[str], Tuple[int, str, float]]


def fetch(url: str, timeout: float = 20.0) -> Tuple[int, str, float]:
    """(status, body, seconds). Network failures return status 0."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "opencre-health-check/1.0"}
    )
    start = time.time()
    try:
        with urllib.request.urlopen(
            req, timeout=timeout
        ) as resp:  # noqa: S310 - operator-supplied URL
            return (
                resp.status,
                resp.read().decode("utf-8", "replace"),
                time.time() - start,
            )
    except urllib.error.HTTPError as err:
        return err.code, "", time.time() - start
    except Exception:  # noqa: BLE001
        return 0, "", time.time() - start


def _json_list_nonempty(body: str) -> bool:
    try:
        data = json.loads(body)
    except ValueError:
        return False
    if isinstance(data, dict):
        data = (
            data.get("standards") or data.get("data") or next(iter(data.values()), None)
        )
    return isinstance(data, list) and len(data) > 0


def run_checks(
    base_url: str, *, get: Fetch = fetch, require_api: bool = True
) -> List[Dict[str, Any]]:
    base = base_url.rstrip("/")
    results: List[Dict[str, Any]] = []

    def check(name: str, path: str, ok: Callable[[int, str], bool]) -> None:
        status, body, secs = get(base + path)
        passed = ok(status, body)
        slow = secs > SLOW_SECONDS
        results.append(
            {
                "check": name,
                "url": base + path,
                "status": status,
                "seconds": round(secs, 2),
                "ok": passed and not slow,
                "slow": slow,
            }
        )

    check("home page answers", "/", lambda s, b: s == 200)
    if require_api:
        check(
            "standards list has data",
            "/rest/v1/standards",
            lambda s, b: s == 200 and _json_list_nonempty(b),
        )
        check(
            "gap-analysis standards list has data",
            "/rest/v1/ga_standards",
            lambda s, b: s == 200 and _json_list_nonempty(b),
        )
    return results


def summarize(results: List[Dict[str, Any]]) -> str:
    bad = [r for r in results if not r["ok"]]
    lines = [
        f"- {r['check']}: HTTP {r['status']} in {r['seconds']}s"
        + (" (too slow)" if r["slow"] else "")
        for r in bad
    ]
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env", choices=sorted(ENVIRONMENTS), help="production or staging")
    ap.add_argument("--base-url", help="override the URL to check")
    ap.add_argument(
        "--no-api",
        action="store_true",
        help="only check the home page (e.g. when the API needs login)",
    )
    ap.add_argument(
        "--notify",
        action="store_true",
        help="alert on failure via ALERT_WEBHOOK_URL / NTFY_URL",
    )
    ap.add_argument(
        "--json", action="store_true", help="print machine-readable results"
    )
    a = ap.parse_args(argv)
    base = a.base_url or ENVIRONMENTS.get(a.env or "")
    if not base:
        ap.error("give --env or --base-url")
    results = run_checks(base, require_api=not a.no_api)
    healthy = all(r["ok"] for r in results)
    if a.json:
        print(json.dumps({"base_url": base, "healthy": healthy, "checks": results}))
    else:
        for r in results:
            print(
                ("ok   " if r["ok"] else "FAIL ")
                + f"{r['check']}: HTTP {r['status']} in {r['seconds']}s"
            )
    if not healthy and a.notify:
        from scripts.ops.notify import send_alert

        sent = send_alert(f"OpenCRE health check failed: {base}", summarize(results))
        print(
            f"alert sent via: {', '.join(sent) or 'nothing configured'}",
            file=sys.stderr,
        )
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
