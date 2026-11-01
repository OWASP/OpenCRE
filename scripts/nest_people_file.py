#!/usr/bin/env python3
"""Write the ``--people-file`` for scripts/ingest_youtube.py: OWASP Nest project leaders, one name per line.

    python scripts/nest_people_file.py --out leaders.txt                       # live; needs NEST_API_KEY
    python scripts/nest_people_file.py --from-json nest-projects.json --out leaders.txt   # offline

``--from-json`` takes an already saved Nest dump: a list of project detail records (or an object with a
``projects`` list), each with ``leaders: [{"name": ...}]``. Names are deduplicated and sorted. Live mode
reads every project once (same endpoints and NEST_API_KEY / NEST_API_BASE as scripts/nest_loader.py);
``--save-json`` keeps what it read so the next run can be offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List

from application.utils.comprehension import nest_source as ns


def load_details(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("projects") or data.get("items") or []
    return [d for d in data if isinstance(d, dict)]


def fetch_details() -> List[dict]:
    import requests

    base = os.environ.get("NEST_API_BASE", "https://nest.owasp.org/api/v0").rstrip("/")
    headers = {"X-API-Key": os.environ["NEST_API_KEY"], "Accept": "application/json"}

    def get(path: str) -> Any:
        r = requests.get(f"{base}/{path.lstrip('/')}", headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()

    out: List[dict] = []
    for it in ns.iter_items(get, "projects/"):
        try:
            out.append(get(f"projects/{it['key']}"))
        except Exception as exc:  # noqa: BLE001 - skip one broken project
            print(f"{it.get('key')}: detail failed {str(exc)[:80]}", file=sys.stderr)
    return out


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-json", help="saved Nest project dump (offline)")
    ap.add_argument("--save-json", help="live mode: also save the fetched records here")
    ap.add_argument("--out", default="", help="output file (default: stdout)")
    a = ap.parse_args(argv)

    if a.from_json:
        details = load_details(a.from_json)
    elif os.environ.get("NEST_API_KEY"):
        details = fetch_details()
        if a.save_json:
            with open(a.save_json, "w", encoding="utf-8") as fh:
                json.dump(details, fh)
    else:
        print("NEST_API_KEY is required (or pass --from-json)", file=sys.stderr)
        return 2

    names = ns.leader_names(iter(details))
    text = "".join(n + "\n" for n in names)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    print(f"{len(names)} leaders from {len(details)} projects", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
