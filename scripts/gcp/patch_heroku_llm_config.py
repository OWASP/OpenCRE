#!/usr/bin/env python3
"""PATCH selected Heroku config vars. Never prints secret values.

Env:
  HEROKU_API_KEY     required
  HEROKU_APP         required (e.g. opencreorg)
  GEMINI_API_KEY     required
  GOOGLE_PROJECT_ID  required
  GOOGLE_PROJECT_LOCATION  default us-central1
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


class _MissingEnv(Exception):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"missing env {name}", file=sys.stderr)
        raise _MissingEnv(name)
    return value


def main() -> int:
    try:
        token = _require("HEROKU_API_KEY")
        app = _require("HEROKU_APP")
        gemini = _require("GEMINI_API_KEY")
        project_id = _require("GOOGLE_PROJECT_ID")
    except _MissingEnv:
        return 2
    location = os.environ.get("GOOGLE_PROJECT_LOCATION", "us-central1").strip() or "us-central1"

    payload = {
        "GEMINI_API_KEY": gemini,
        "GOOGLE_PROJECT_ID": project_id,
        "GOOGLE_PROJECT_LOCATION": location,
        "CRE_LLM_CHAT_MODEL": "gemini/gemini-2.5-flash",
        "CRE_EMBED_MODEL": "gemini/gemini-embedding-001",
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.heroku.com/apps/{app}/config-vars",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.heroku+json; version=3",
            "Content-Type": "application/json",
            "User-Agent": "OpenCRE-gcp-iac/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.getcode()
            resp.read()
    except urllib.error.HTTPError as err:
        print(f"heroku PATCH failed HTTP {err.code}", file=sys.stderr)
        return 1
    except urllib.error.URLError as err:
        print(f"heroku PATCH network error: {type(err.reason).__name__}", file=sys.stderr)
        return 1
    if status not in (200, 201):
        print(f"heroku PATCH unexpected status {status}", file=sys.stderr)
        return 1
    print("heroku config patched for keys:", ", ".join(sorted(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
