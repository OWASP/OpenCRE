#!/usr/bin/env python3
"""Health check run ON the staging homeserver (needs the docker CLI; stdlib only).

    python3 staging_host_health.py                       # print results, exit 1 if anything is wrong
    python3 staging_host_health.py --notify              # also alert (ALERT_WEBHOOK_URL / NTFY_URL)

What it checks every run: all containers are up (and healthy where Docker reports it), the web page
answers locally, web and MCP carry the same answer settings and exactly the expected ones, the
containers are not logging a burst of errors, and the disk is not nearly full. Alerts are sent when
the set of problems changes and repeated at most every --cooldown minutes; a "recovered" message follows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from typing import Callable, Dict, List, Optional, Sequence

REQUIRED = ["web", "mcp", "edge", "db", "redis", "neo4j"]
EXPECTED_FLAGS = {
    "OWASP_CX_LONGCTX": "1",
    "OWASP_CX_LONGCTX_CHARS": "2000000",
    "OWASP_CX_PREFIXCACHE": "1",
    "ANSWER_LOG_ENABLED": "1",
}
PREFIX = "opencre-staging-"

Runner = Callable[[Sequence[str]], str]


def sh(cmd: Sequence[str]) -> str:
    try:
        return subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=60
        ).stdout
    except Exception:  # noqa: BLE001
        return ""


def check_containers(run: Runner) -> List[str]:
    out = run(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"])
    status = dict(line.split("|", 1) for line in out.splitlines() if "|" in line)
    problems = []
    for name in REQUIRED:
        found = [s for n, s in status.items() if n.startswith(PREFIX + name)]
        if not found or not all(s.startswith("Up") for s in found):
            problems.append(f"container {name} is not running")
        elif any("unhealthy" in s or "starting" in s for s in found):
            problems.append(f"container {name} is not healthy")
    if not any(n.startswith(PREFIX + "worker") for n in status):
        problems.append("no worker containers are running")
    return problems


def _env(run: Runner, container: str) -> Dict[str, str]:
    out = run(["docker", "exec", container, "printenv"])
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def check_flags(run: Runner, expected: Dict[str, str]) -> List[str]:
    web, mcp = _env(run, PREFIX + "web-1"), _env(run, PREFIX + "mcp-1")
    if not web or not mcp:
        return ["cannot read settings from the web/mcp containers"]
    keep = lambda e: {
        k: v for k, v in e.items() if k.startswith("OWASP_CX_") or k in expected
    }  # noqa: E731
    web, mcp = keep(web), keep(mcp)
    problems = []
    if web != mcp:
        problems.append(
            "web and mcp have different answer settings: "
            + json.dumps(
                {
                    k: [web.get(k), mcp.get(k)]
                    for k in sorted(set(web) | set(mcp))
                    if web.get(k) != mcp.get(k)
                }
            )
        )
    for k, v in expected.items():
        if mcp.get(k) != v:
            problems.append(f"setting {k} is {mcp.get(k)!r}, expected {v!r}")
    for k in mcp:
        if k.startswith("OWASP_CX_") and k not in expected:
            problems.append(f"unexpected setting {k}={mcp[k]}")
    return problems


def check_web(get: Optional[Callable[[str], int]] = None) -> List[str]:
    def _get(url: str) -> int:
        try:
            with urllib.request.urlopen(
                url, timeout=15
            ) as r:  # noqa: S310 - fixed local URL
                return r.status
        except Exception:  # noqa: BLE001
            return 0

    status = (get or _get)("http://127.0.0.1:5003/")
    return [] if status == 200 else [f"web answers HTTP {status} on 127.0.0.1:5003"]


def check_logs(run: Runner, limit: int = 25) -> List[str]:
    problems = []
    for name in ("mcp-1", "web-1"):
        out = run(["docker", "logs", "--since", "10m", PREFIX + name])
        errors = sum(
            1
            for line in out.splitlines()
            if '"level": "ERROR"' in line and "LiteLLM" not in line
        )
        if errors > limit:
            problems.append(f"{name} logged {errors} errors in the last 10 minutes")
    return problems


def check_disk(run: Runner, path: str = "/", limit: int = 90) -> List[str]:
    out = run(["df", "--output=pcent", path]).split()
    try:
        used = int(out[-1].strip("%"))
    except (IndexError, ValueError):
        return []
    return [f"disk {path} is {used}% full"] if used >= limit else []


def collect(
    run: Runner = sh, expected: Optional[Dict[str, str]] = None, get=None
) -> List[str]:
    return (
        check_containers(run)
        + check_web(get)
        + check_flags(run, expected or EXPECTED_FLAGS)
        + check_logs(run)
        + check_disk(run)
    )


def decide(
    problems: List[str],
    state: Dict[str, float | str],
    *,
    now: float,
    cooldown_minutes: float,
) -> Optional[str]:
    """'alert', 'recovered' or None, given the previous state (mutated in place)."""
    digest = (
        hashlib.sha1("\n".join(sorted(problems)).encode()).hexdigest()
        if problems
        else ""
    )
    prev, last = str(state.get("digest", "")), float(state.get("alerted_at", 0) or 0)
    state["digest"] = digest
    if problems:
        if digest != prev or now - last >= cooldown_minutes * 60:
            state["alerted_at"] = now
            return "alert"
        return None
    if prev:
        state["alerted_at"] = 0
        return "recovered"
    return None


def main(argv: Optional[List[str]] = None, run: Runner = sh) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--state", default="/var/tmp/opencre-health.state")
    ap.add_argument(
        "--cooldown",
        type=float,
        default=60.0,
        help="minutes between repeated alerts for the same problems",
    )
    ap.add_argument(
        "--expect",
        nargs="*",
        default=None,
        metavar="KEY=VALUE",
        help="replace the expected settings",
    )
    a = ap.parse_args(argv)
    expected = dict(kv.split("=", 1) for kv in a.expect) if a.expect else None
    problems = collect(run, expected)
    for p in problems:
        print("PROBLEM:", p)
    if not problems:
        print("all checks passed")
    if a.notify:
        try:
            state = json.load(open(a.state))
        except Exception:  # noqa: BLE001
            state = {}
        action = decide(problems, state, now=time.time(), cooldown_minutes=a.cooldown)
        try:
            json.dump(state, open(a.state, "w"))
        except OSError:
            pass
        if action:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from scripts.ops.notify import send_alert

            if action == "alert":
                send_alert("OpenCRE staging needs attention", "\n".join(problems))
            else:
                send_alert(
                    "OpenCRE staging recovered",
                    "All checks pass again.",
                    priority="default",
                )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
