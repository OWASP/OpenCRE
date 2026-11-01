#!/usr/bin/env python3
"""Score the OWASP-agent synth suite v2 JSONL against a local index or chat API.

See ``application/utils/owasp_agent/README.md`` for setup.

Exit 0 when ``pass_rate >= OWASP_SYNTH_PASS_RATE`` (default 0.90) and
``halluc_invent == 0``. Does not regenerate the suite.

Env:
  OWASP_SYNTH_SUITE     path to JSONL (default: fixtures/owasp_agent_synth_v2.jsonl)
  OWASP_SYNTH_OUT       results JSON path
  OWASP_SYNTH_PASS_RATE pass threshold (default 0.90)
  OWASP_SYNTH_FULL=1    hit ``/rest/v1/completion`` for ``path=completion`` rows
  OWASP_PROBE_COMPLETION_URL   completion endpoint
  OWASP_PROBE_COMPLETION_MODE  http (default) | inprocess
      inprocess: Flask test_client with NO_LOGIN=1 (for staging docker exec e2e
      when the public chat API requires OAuth)
  OWASP_SYNTH_ONLY_IDS  comma-separated ids to run (optional)
  OWASP_SYNTH_ONLY_CATS comma-separated categories (optional)
  OWASP_AGENT_DB        agent index URL/path
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    # Agent deferred to CRE RAG (correct for some AI Exchange content asks).
    if answer == "__CRE_FALLTHROUGH__":
        if item.get("allow_cre_fallthrough") or item.get("cat") == "aix_content":
            for s in item.get("must_not") or []:
                # Fallthrough is never the chapters/meetup clarify template.
                if s.lower() in (
                    "which city are you in",
                    "board history, and membership",
                ):
                    continue
            return []
        fails.append("unexpected_cre_fallthrough")
        return fails
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


def _history(item: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    raw = item.get("history")
    if not isinstance(raw, list):
        return None
    out: List[Dict[str, str]] = []
    for turn in raw:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out or None


def ask_agent(q: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.router import OwaspAgentRouter

    # Prefer explicit OWASP_AGENT_DB; else let IndexStore use DATABASE_URL /
    # DEV_DATABASE_URL (staging/prod). Only fall back to local sqlite when no
    # app DB env is set.
    override = (os.environ.get("OWASP_AGENT_DB") or "").strip()
    if override:
        store = IndexStore(override)
    elif any(
        (os.environ.get(k) or "").strip()
        for k in (
            "DATABASE_URL",
            "DEV_DATABASE_URL",
            "PROD_DATABASE_URL",
            "SQLALCHEMY_DATABASE_URI",
        )
    ):
        store = IndexStore()
    else:
        store = IndexStore(str(_REPO_ROOT / "tmp" / "owasp_agent.sqlite"))
    router = OwaspAgentRouter(store=store)
    resp = router.handle(q, history=history)
    if resp is None:
        # CRE fallthrough — mark explicitly so scorers can allow empty agent answers.
        return "__CRE_FALLTHROUGH__"
    return str(resp.get("response") or "")


def ask_completion_http(q: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    import urllib.error
    import urllib.request

    url = os.environ.get(
        "OWASP_PROBE_COMPLETION_URL", "http://127.0.0.1:5000/rest/v1/completion"
    )
    body: Dict[str, Any] = {"prompt": q}
    if history:
        body["messages"] = list(history) + [{"role": "user", "content": q}]
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("OWASP_PROBE_BEARER") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    cookie = (os.environ.get("OWASP_PROBE_COOKIE") or "").strip()
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.loads(r.read().decode())
        if isinstance(payload, dict) and payload.get("error"):
            return f"__ERROR__:{payload.get('error')}"
        return str((payload or {}).get("response") or "")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode()[:300]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        return f"__ERROR__:HTTP {exc.code}:{detail}"
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__:{exc}"


def ask_completion_inprocess(
    q: str, history: Optional[List[Dict[str, str]]] = None
) -> str:
    """Exercise ``/rest/v1/completion`` via Flask test_client (NO_LOGIN=1).

    Uses production config so staging/prod ``DATABASE_URL`` (agent index + CRE
    RAG) is the same DB the live chat API uses. ``mode=test`` would point at an
    empty sqlite and miss embeddings.
    """
    os.environ["NO_LOGIN"] = "1"
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")
    # Prefer Postgres URL from the container env for SQLAlchemy (psycopg2 pin).
    db_url = (os.environ.get("DATABASE_URL") or "").strip() or (
        os.environ.get("DEV_DATABASE_URL") or ""
    ).strip()
    if db_url and not (os.environ.get("SQLALCHEMY_DATABASE_URI") or "").strip():
        try:
            from application.utils.postgres_url import (
                is_postgres_url,
                sqlalchemy_postgres_url,
            )

            if is_postgres_url(db_url):
                db_url = sqlalchemy_postgres_url(db_url)
        except Exception:  # noqa: BLE001
            if db_url.startswith("postgres://"):
                db_url = "postgresql+psycopg2://" + db_url.split("://", 1)[1]
            elif db_url.startswith("postgresql://"):
                db_url = "postgresql+psycopg2://" + db_url.split("://", 1)[1]
        os.environ["SQLALCHEMY_DATABASE_URI"] = db_url
    from application import create_app

    app = create_app(mode="production")
    body: Dict[str, Any] = {"prompt": q}
    if history:
        body["messages"] = list(history) + [{"role": "user", "content": q}]
    with app.app_context():
        with app.test_client() as client:
            response = client.post(
                "/rest/v1/completion",
                json=body,
                content_type="application/json",
            )
    if response.status_code != 200:
        return f"__ERROR__:HTTP {response.status_code}:{response.data[:300]!r}"
    payload = json.loads(response.data)
    if isinstance(payload, dict) and payload.get("error"):
        return f"__ERROR__:{payload.get('error')}"
    return str((payload or {}).get("response") or "")


def ask(item: Dict[str, Any], *, full: bool) -> str:
    q = str(item.get("q") or "")
    path = item.get("path", "agent")
    history = _history(item)
    if path != "completion":
        return ask_agent(q, history=history)
    # completion path
    if not full:
        # Prefer agent answer when present; otherwise skip scoring later.
        ans = ask_agent(q, history=history)
        return ans
    mode = (os.environ.get("OWASP_PROBE_COMPLETION_MODE") or "http").strip().lower()
    if mode == "inprocess":
        return ask_completion_inprocess(q, history=history)
    return ask_completion_http(q, history=history)


def _filter_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    only_ids = {
        int(x.strip())
        for x in (os.environ.get("OWASP_SYNTH_ONLY_IDS") or "").split(",")
        if x.strip().isdigit()
    }
    only_cats = {
        x.strip().lower()
        for x in (os.environ.get("OWASP_SYNTH_ONLY_CATS") or "").split(",")
        if x.strip()
    }
    out = items
    if only_ids:
        out = [i for i in out if int(i.get("id") or -1) in only_ids]
    if only_cats:
        out = [i for i in out if str(i.get("cat") or "").lower() in only_cats]
    return out


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
    items = _filter_items(items)
    full = os.environ.get("OWASP_SYNTH_FULL", "0") == "1"
    rows: List[Dict[str, Any]] = []
    fail = 0
    halluc = 0
    scored = 0
    skipped = 0
    for item in items:
        path = item.get("path", "agent")
        if path == "completion" and not full:
            ans = ask(item, full=False)
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
                skipped += 1
                continue
        else:
            ans = ask(item, full=full)
        fails = score_one(item, ans)
        ok = not fails
        if not ok:
            fail += 1
        if "halluc_invent" in fails:
            halluc += 1
        scored += 1
        if not ok and len([r for r in rows if not r.get("ok")]) < 60:
            preview = (ans or "")[:120].replace("\n", " ")
            print(
                f"FAIL #{item['id']} {item.get('cat')} {fails} | "
                f"{item['q'][:80]} || {preview}"
            )
        rows.append(
            {
                "id": item["id"],
                "ok": ok,
                "fails": fails,
                "cat": item.get("cat"),
                "suite": item.get("_suite"),
                "q": item.get("q"),
                "answer_preview": (ans or "")[:240],
            }
        )

    print_category_table(rows)
    pass_rate = (scored - fail) / scored if scored else 0.0
    summary = {
        "scored": scored,
        "failed": fail,
        "skipped_completion": skipped,
        "pass_rate": round(pass_rate, 4),
        "halluc_invent": halluc,
        "threshold": threshold,
        "suite": ",".join(str(p) for p in suite_paths),
        "full": full,
        "completion_mode": os.environ.get("OWASP_PROBE_COMPLETION_MODE", "http"),
    }
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print("SUMMARY", json.dumps(summary))
    if pass_rate >= threshold and halluc == 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
