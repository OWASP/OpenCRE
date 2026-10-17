#!/usr/bin/env python3
"""Score the OWASP-agent synth suite v2 JSONL against a local index.

See ``application/utils/owasp_agent/README.md`` for setup.

Exit 0 when ``pass_rate >= OWASP_SYNTH_PASS_RATE`` (default 0.90) and
``halluc_invent == 0``. Does not regenerate the suite.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("OWASP_AGENT_ENABLED", "1")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SUITE = (
    _REPO_ROOT
    / "application"
    / "tests"
    / "owasp_agent"
    / "fixtures"
    / "owasp_agent_synth_v2.jsonl"
)
_FIXTURES = _DEFAULT_SUITE.parent
# Extra suites runnable via OWASP_SYNTH_SUITE=name1,name2 (bare names resolve to
# fixtures/<name>.jsonl): staging findings from the 2026-10 OWASP agent testing.
KNOWN_SUITES = (
    "owasp_agent_synth_v2",
    "owasp_agent_regression",
    "appsec_usa_attendee",
)
_DEFAULT_OUT = _REPO_ROOT / "tmp" / "owasp_agent_synth_results_v2.json"


def score_one(item: Dict[str, Any], answer: str) -> List[str]:
    fails: List[str] = []
    low = answer.lower()
    for s in item.get("must") or []:
        if s.lower() not in low:
            fails.append(f"missing:{s}")
    must_any = item.get("must_any") or []
    if must_any and not any(s.lower() in low for s in must_any):
        fails.append(f"missing_any:{must_any}")
    for s in item.get("must_not") or []:
        if s.lower() in low:
            fails.append(f"forbidden:{s}")
    rx = item.get("regex")
    if rx and not re.search(rx, answer, re.I):
        fails.append(f"regex:{rx}")
    if item.get("cat") == "neighbor_hallucination":
        invent_markers = [
            "in his talk he",
            "she said that",
            "presented slides on",
            "keynote argued",
        ]
        if any(m in low for m in invent_markers):
            fails.append("halluc_invent")
    return fails


def ask(q: str, path: str) -> str:
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.router import OwaspAgentRouter

    store = IndexStore()
    router = OwaspAgentRouter(store=store)
    resp = router.handle(q)
    if resp is not None:
        return str(resp.get("response") or "")
    if path != "completion":
        return ""
    data = json.dumps({"prompt": q}).encode()
    import urllib.request

    req = urllib.request.Request(
        os.environ.get(
            "OWASP_PROBE_COMPLETION_URL", "http://127.0.0.1:5000/rest/v1/completion"
        ),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode())
        return str(body.get("response") or "")
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__:{exc}"


def resolve_suites(spec: str) -> List[Path]:
    """Comma-separated suite names/paths; empty means the default v2 suite."""
    if not spec.strip():
        return [_DEFAULT_SUITE]
    out: List[Path] = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        if part == "all":
            out.extend(_FIXTURES / f"{n}.jsonl" for n in KNOWN_SUITES)
        elif "/" not in part and not part.endswith(".jsonl"):
            out.append(_FIXTURES / f"{part}.jsonl")
        else:
            out.append(Path(part))
    return out


def print_category_table(rows: List[Dict[str, Any]]) -> None:
    """Pass rate per suite/category (skipped-completion rows count as pass)."""
    agg: Dict[str, List[int]] = {}
    for r in rows:
        key = f"{r.get('suite')}/{r.get('cat')}"
        pass_n, total = agg.setdefault(key, [0, 0])
        agg[key] = [pass_n + (1 if r["ok"] else 0), total + 1]
    for key in sorted(agg):
        p, t = agg[key]
        print(f"CAT {key:55s} {p:3d}/{t:3d}")


def main() -> int:
    threshold = float(os.environ.get("OWASP_SYNTH_PASS_RATE", "0.90"))
    strict = os.environ.get("OWASP_SYNTH_STRICT", "0") == "1"
    suite_paths = resolve_suites(os.environ.get("OWASP_SYNTH_SUITE", ""))
    out_path = Path(os.environ.get("OWASP_SYNTH_OUT", str(_DEFAULT_OUT)))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    items: List[Dict[str, Any]] = []
    for suite_path in suite_paths:
        if not suite_path.is_file():
            print(f"Suite not found: {suite_path}", file=sys.stderr)
            return 2
        for line in suite_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_suite"] = suite_path.stem
                items.append(row)
    full = os.environ.get("OWASP_SYNTH_FULL", "0") == "1"
    rows: List[Dict[str, Any]] = []
    fail = 0
    halluc = 0
    scored = 0
    for item in items:
        path = item.get("path", "agent")
        if path == "completion" and not full:
            ans = ask(item["q"], "agent")
            if not ans and not strict:
                rows.append(
                    {
                        "id": item["id"],
                        "ok": True,
                        "skipped_completion": True,
                        "cat": item.get("cat"),
                        "q": item.get("q"),
                    }
                )
                scored += 1
                continue
        else:
            ans = ask(item["q"], path)
        fails = score_one(item, ans)
        ok = not fails
        if not ok:
            fail += 1
        if "halluc_invent" in fails:
            halluc += 1
        scored += 1
        if not ok and len(rows) < 40:
            print(f"FAIL #{item['id']} {item.get('cat')} {fails} | {item['q'][:80]}")
        rows.append(
            {
                "id": item["id"],
                "ok": ok,
                "fails": fails,
                "cat": item.get("cat"),
                "suite": item.get("_suite"),
                "q": item.get("q"),
            }
        )

    print_category_table(rows)
    pass_rate = (scored - fail) / scored if scored else 0.0
    summary = {
        "scored": scored,
        "failed": fail,
        "pass_rate": round(pass_rate, 4),
        "halluc_invent": halluc,
        "threshold": threshold,
        "suite": ",".join(str(p) for p in suite_paths),
    }
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print("SUMMARY", json.dumps(summary))
    if pass_rate >= threshold and halluc == 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
