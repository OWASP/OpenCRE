"""Send an alert to whatever is configured: a Slack/Discord-style webhook and/or an ntfy.sh topic.

Nothing is configured by default, so every function is a safe no-op without keys:
  ALERT_WEBHOOK_URL   Slack or Discord incoming webhook (sends {"text": ..., "content": ...})
  NTFY_URL            full topic URL, e.g. https://ntfy.sh/opencre-staging-<random>
Never raises: an alert path that crashes would hide the incident it is reporting.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Dict, List


def _post(url: str, data: bytes, headers: Dict[str, str], timeout: float) -> bool:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(
            req, timeout=timeout
        ) as resp:  # noqa: S310 - operator-supplied URL
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001
        return False


def send_alert(
    title: str, body: str, *, priority: str = "high", timeout: float = 10.0
) -> List[str]:
    """Deliver to every configured channel; returns the names that accepted it."""
    delivered: List[str] = []
    hook = (os.environ.get("ALERT_WEBHOOK_URL") or "").strip()
    if hook:
        text = f"*{title}*\n{body}"
        payload = json.dumps({"text": text, "content": text}).encode()
        if _post(hook, payload, {"Content-Type": "application/json"}, timeout):
            delivered.append("webhook")
    ntfy = (os.environ.get("NTFY_URL") or "").strip()
    if ntfy:
        headers = {"Title": title[:100], "Priority": priority, "Tags": "rotating_light"}
        if _post(ntfy, body.encode(), headers, timeout):
            delivered.append("ntfy")
    return delivered
