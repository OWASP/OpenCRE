#!/usr/bin/env python3
"""Create the uptime monitors in ops/uptime-monitors.json on UptimeRobot (idempotent, stdlib only).

    python scripts/ops/sync_uptime_monitors.py            # dry run: prints what would be created
    UPTIMEROBOT_API_KEY=... UPTIMEROBOT_ALERT_CONTACTS=0123456_0_0 \
        python scripts/ops/sync_uptime_monitors.py --apply

Without UPTIMEROBOT_API_KEY it never talks to the network. Monitors are matched by URL, so running it twice
creates nothing new. Prefer a free-plan API key that only has the monitors of this project.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List

API = "https://api.uptimerobot.com/v2"
TYPE_CODES = {"http": 1, "keyword": 2}

Post = Callable[[str, Dict[str, str]], Dict[str, Any]]


def _post(endpoint: str, fields: Dict[str, str]) -> Dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        f"{API}/{endpoint}",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(
        req, timeout=30
    ) as resp:  # noqa: S310 - fixed https endpoint
        return json.loads(resp.read().decode())


def plan(config: Dict[str, Any], existing_urls: List[str]) -> List[Dict[str, Any]]:
    """Monitors in the config whose URL is not on the account yet."""
    have = {u.rstrip("/") for u in existing_urls}
    return [m for m in config["monitors"] if m["url"].rstrip("/") not in have]


def create_fields(
    api_key: str, monitor: Dict[str, Any], interval: int, contacts: str
) -> Dict[str, str]:
    fields = {
        "api_key": api_key,
        "format": "json",
        "friendly_name": monitor["name"],
        "url": monitor["url"],
        "type": str(TYPE_CODES[monitor.get("type", "http")]),
        "interval": str(interval),
    }
    if monitor.get("type") == "keyword":
        fields.update(
            keyword_type="2", keyword_value=monitor["keyword"]
        )  # alert when the keyword is missing
    if contacts:
        fields["alert_contacts"] = contacts
    return fields


def main(argv: List[str] | None = None, post: Post = _post) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "ops", "uptime-monitors.json"
        ),
    )
    ap.add_argument(
        "--apply", action="store_true", help="really create the missing monitors"
    )
    a = ap.parse_args(argv)
    config = json.load(open(a.config, encoding="utf-8"))
    key = (os.environ.get("UPTIMEROBOT_API_KEY") or "").strip()
    contacts = (os.environ.get("UPTIMEROBOT_ALERT_CONTACTS") or "").strip()
    if not key:
        print("UPTIMEROBOT_API_KEY not set: dry run, nothing contacted.")
        for m in config["monitors"]:
            print(f"  would ensure: {m['name']}  ->  {m['url']}")
        return 0
    existing = post("getMonitors", {"api_key": key, "format": "json"})
    if existing.get("stat") != "ok":
        print(
            f"UptimeRobot refused the request: {existing.get('error')}", file=sys.stderr
        )
        return 2
    todo = plan(config, [m["url"] for m in existing.get("monitors", [])])
    for m in todo:
        if not a.apply:
            print(f"  would create: {m['name']}")
            continue
        out = post(
            "newMonitor",
            create_fields(key, m, int(config.get("interval_seconds", 300)), contacts),
        )
        print(f"  {'created' if out.get('stat') == 'ok' else 'FAILED'}: {m['name']}")
    if not todo:
        print("all monitors already exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
