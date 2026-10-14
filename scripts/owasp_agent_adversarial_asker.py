#!/usr/bin/env python3
"""Temporary adversarial asker against ``/rest/v1/completion`` (max 500 turns).

Does **not** load the synth suite or agent fixtures. It only knows the product
contract at a high level: the OWASP chat completion endpoint should answer
factual questions about OWASP chapters, projects, leaders, board, events,
membership, and well-known CRE / AI Exchange concepts when the answer is
knowable from public OWASP metadata — not invent, and not refuse with a
generic chapters/meetup clarify when the question is clearly in-domain.

For each turn it:
  1. Generates an edge-case question (template bank + light paraphrases)
  2. POSTs to the completion endpoint
  3. Heuristically judges refuse / wrong / ok
  4. Records failures for promotion into the synth suite

Env:
  OWASP_PROBE_COMPLETION_URL   default http://127.0.0.1:5001/rest/v1/completion
  OWASP_PROBE_COMPLETION_MODE  http | inprocess
  OWASP_ADV_MAX_TURNS          default 500
  OWASP_ADV_OUT                default tmp/owasp_agent_adversarial_failures.jsonl
  OWASP_ADV_SEED               optional int
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO / "tmp" / "owasp_agent_adversarial_failures.jsonl"

# High-level contract only — not the synth suite.
REFUSAL_MARKERS = (
    "which city are you in",
    "i don't have",
    "i do not have",
    "i'm not sure",
    "i am not sure",
    "cannot find",
    "can't find",
    "no information",
    "don't know",
    "do not know",
    "unable to answer",
    "out of scope",
    "board history, and membership",
    "please clarify",
    "could you clarify",
)

GENERIC_WRONG_MARKERS = (
    "as an ai language model",
    "i cannot assist with that",
)


@dataclass
class Case:
    q: str
    expect: str  # must_contain | must_any | must_not_refuse | cre_ok
    needles: Tuple[str, ...]
    note: str
    cat: str


def _bank(rng: random.Random) -> List[Case]:
    """Edge-case bank grounded in public OWASP knowledge, not our fixtures."""
    chapters = [
        ("London", ("london",)),
        ("New York", ("new york", "nyc")),
        ("Tokyo", ("tokyo",)),
        ("São Paulo", ("são paulo", "sao paulo")),
        ("Berlin", ("berlin",)),
        ("Bangalore", ("bangalore", "bengaluru")),
    ]
    projects = [
        ("ASVS", ("asvs", "application security verification")),
        ("Top Ten", ("top 10", "top ten")),
        ("Cheat Sheet Series", ("cheat sheet",)),
        ("Juice Shop", ("juice shop",)),
        ("Dependency-Check", ("dependency-check", "dependency check")),
        ("Amass", ("amass",)),
    ]
    people = [
        ("Rob van der Veer", ("rob", "van der veer", "ai exchange")),
        ("Andrew van der Stock", ("andrew", "van der stock")),
        ("OWASP board", ("board",)),
    ]
    cases: List[Case] = []

    for city, needles in chapters:
        cases.append(
            Case(
                q=f"Does OWASP have a chapter in {city}?",
                expect="must_any",
                needles=needles + ("chapter", "yes", "leaders", "meetup"),
                note="chapter existence",
                cat="chapter_edge",
            )
        )
        cases.append(
            Case(
                q=f"Who leads the OWASP {city} chapter?",
                expect="must_not_refuse",
                needles=(),
                note="chapter leaders",
                cat="chapter_edge",
            )
        )
        cases.append(
            Case(
                q=f"OWASP {city} chapter contact / meetup?",
                expect="must_not_refuse",
                needles=(),
                note="chapter contact paraphrase",
                cat="chapter_edge",
            )
        )

    for name, needles in projects:
        cases.append(
            Case(
                q=f"What is the OWASP {name} project?",
                expect="must_any",
                needles=needles,
                note="project identity",
                cat="project_edge",
            )
        )
        cases.append(
            Case(
                q=f"Who are the leaders of OWASP {name}?",
                expect="must_not_refuse",
                needles=(),
                note="project leaders",
                cat="project_edge",
            )
        )

    for name, needles in people:
        cases.append(
            Case(
                q=f"Who is {name}?",
                expect="must_any",
                needles=needles,
                note="person identity",
                cat="people_edge",
            )
        )
        cases.append(
            Case(
                q=f"Tell me about {name} at OWASP",
                expect="must_not_refuse",
                needles=(),
                note="person paraphrase",
                cat="people_edge",
            )
        )

    aix = [
        Case(
            q="What is the lethal trifecta in agentic AI according to OWASP AI Exchange?",
            expect="must_any",
            needles=(
                "trifecta",
                "prompt injection",
                "exfiltration",
                "sensitive data",
                "three",
            ),
            note="aix trifecta",
            cat="aix_edge",
        ),
        Case(
            q="OWASP AI Exchange: lethal trifecta for data leakage?",
            expect="must_any",
            needles=("trifecta", "attacker", "sensitive", "exfil"),
            note="aix trifecta short",
            cat="aix_edge",
        ),
        Case(
            q="Explain the OWASP AI Exchange lethal trifecta without naming AI Exchange",
            expect="must_not_refuse",
            needles=(),
            note="aix without brand",
            cat="aix_edge",
        ),
    ]
    cases.extend(aix)

    membership = [
        Case(
            q="How much is OWASP membership in the United States?",
            expect="must_not_refuse",
            needles=(),
            note="membership fee US",
            cat="membership_edge",
        ),
        Case(
            q="OWASP membership cost Germany?",
            expect="must_not_refuse",
            needles=(),
            note="membership fee DE",
            cat="membership_edge",
        ),
    ]
    cases.extend(membership)

    board = [
        Case(
            q="Who is on the current OWASP board?",
            expect="must_not_refuse",
            needles=(),
            note="board roster",
            cat="board_edge",
        ),
        Case(
            q="List OWASP board members for this year",
            expect="must_not_refuse",
            needles=(),
            note="board year",
            cat="board_edge",
        ),
    ]
    cases.extend(board)

    # Ambiguous / trap questions that should clarify — NOT counted as failures
    # when they refuse; we still probe wrong confident answers.
    traps = [
        Case(
            q="Who is the chapter leader?",
            expect="cre_ok",
            needles=(),
            note="ambiguous chapter — clarify ok",
            cat="trap_clarify",
        ),
        Case(
            q="Tell me about the project",
            expect="cre_ok",
            needles=(),
            note="ambiguous project — clarify ok",
            cat="trap_clarify",
        ),
    ]
    cases.extend(traps)

    # Paraphrase mutations
    extras: List[Case] = []
    for c in list(cases):
        if c.cat == "trap_clarify":
            continue
        variants = [
            f"Quick question: {c.q}",
            c.q.replace("?", " please?"),
            f"In one sentence: {c.q}",
            f"OWASP org: {c.q}",
        ]
        for v in variants:
            extras.append(
                Case(
                    q=v,
                    expect=c.expect,
                    needles=c.needles,
                    note=c.note + " / paraphrase",
                    cat=c.cat,
                )
            )
    cases.extend(extras)
    rng.shuffle(cases)
    return cases


def ask_http(q: str) -> str:
    url = os.environ.get(
        "OWASP_PROBE_COMPLETION_URL", "http://127.0.0.1:5001/rest/v1/completion"
    )
    body = json.dumps({"prompt": q}).encode()
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("OWASP_PROBE_BEARER") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    cookie = (os.environ.get("OWASP_PROBE_COOKIE") or "").strip()
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
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


def ask_inprocess(q: str) -> str:
    os.environ["NO_LOGIN"] = "1"
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")
    sys.path.insert(0, str(_REPO))
    db_url = (
        (os.environ.get("DATABASE_URL") or "").strip()
        or (os.environ.get("DEV_DATABASE_URL") or "").strip()
    )
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
    with app.app_context():
        with app.test_client() as client:
            resp = client.post(
                "/rest/v1/completion",
                json={"prompt": q},
                content_type="application/json",
            )
        if resp.status_code >= 400:
            return f"__ERROR__:HTTP {resp.status_code}:{resp.data[:200]!r}"
        payload = json.loads(resp.data)
        return str((payload or {}).get("response") or "")


def ask(q: str) -> str:
    mode = (os.environ.get("OWASP_PROBE_COMPLETION_MODE") or "http").strip().lower()
    if mode == "inprocess":
        return ask_inprocess(q)
    return ask_http(q)


def is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    if not low.strip() or low.startswith("__error__"):
        return True
    return any(m in low for m in REFUSAL_MARKERS)


def judge(case: Case, answer: str) -> Tuple[bool, str]:
    """Return (ok, reason). ok=False means record as adversarial failure."""
    low = (answer or "").lower()
    if low.startswith("__error__"):
        return False, f"http_error:{answer[:120]}"
    if any(m in low for m in GENERIC_WRONG_MARKERS):
        return False, "generic_wrong"

    if case.expect == "cre_ok":
        # Ambiguous traps: refusal/clarify is fine; confident wrong invent is not.
        invent = ("in his talk he", "she said that", "presented slides on")
        if any(m in low for m in invent):
            return False, "halluc_invent"
        return True, "clarify_ok"

    if case.expect == "must_not_refuse":
        if is_refusal(answer):
            return False, "unexpected_refusal"
        return True, "answered"

    if case.expect in ("must_contain", "must_any"):
        if is_refusal(answer):
            return False, "unexpected_refusal"
        if case.needles and not any(n.lower() in low for n in case.needles):
            return False, f"missing_needles:{list(case.needles)}"
        return True, "needles_ok"

    return True, "noop"


def to_synth_row(case: Case, answer: str, reason: str, turn: int) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": 900000 + turn,
        "cat": f"adversarial_{case.cat}",
        "q": case.q,
        "path": "completion",
        "note": f"{case.note}; fail={reason}",
        "adversarial_answer_preview": (answer or "")[:400],
        "adversarial_reason": reason,
    }
    if case.expect == "must_any" and case.needles:
        row["must_any"] = list(case.needles)
    if case.expect == "must_not_refuse":
        row["must_not"] = [
            "which city are you in",
            "board history, and membership",
        ]
    return row


def main() -> int:
    seed = int(os.environ.get("OWASP_ADV_SEED") or "14")
    rng = random.Random(seed)
    max_turns = int(os.environ.get("OWASP_ADV_MAX_TURNS") or "500")
    out_path = Path(os.environ.get("OWASP_ADV_OUT") or str(_DEFAULT_OUT))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bank = _bank(rng)
    # Cycle the bank up to max_turns
    failures: List[Dict[str, Any]] = []
    ok_n = fail_n = 0
    print(
        json.dumps(
            {
                "start": True,
                "max_turns": max_turns,
                "bank": len(bank),
                "url": os.environ.get("OWASP_PROBE_COMPLETION_URL"),
                "mode": os.environ.get("OWASP_PROBE_COMPLETION_MODE", "http"),
            }
        ),
        flush=True,
    )

    with out_path.open("w") as fh:
        for turn in range(1, max_turns + 1):
            case = bank[(turn - 1) % len(bank)]
            # Extra light mutation every 7th turn
            q = case.q
            if turn % 7 == 0:
                q = q + " (source: OWASP.org)"
            t0 = time.time()
            answer = ask(q)
            dt = round(time.time() - t0, 2)
            ok, reason = judge(case, answer)
            if ok:
                ok_n += 1
            else:
                fail_n += 1
                row = to_synth_row(
                    Case(q, case.expect, case.needles, case.note, case.cat),
                    answer,
                    reason,
                    turn,
                )
                failures.append(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(
                    f"FAIL turn={turn} {reason} | {q[:90]} || "
                    f"{(answer or '')[:100].replace(chr(10), ' ')}",
                    flush=True,
                )
            if turn % 25 == 0:
                print(
                    json.dumps(
                        {
                            "progress": turn,
                            "ok": ok_n,
                            "fail": fail_n,
                            "last_dt": dt,
                        }
                    ),
                    flush=True,
                )

    summary_path = out_path.with_suffix(".summary.json")
    summary = {
        "turns": max_turns,
        "ok": ok_n,
        "fail": fail_n,
        "failures_path": str(out_path),
        "failure_ids": [r["id"] for r in failures],
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    print("SUMMARY", json.dumps(summary), flush=True)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
