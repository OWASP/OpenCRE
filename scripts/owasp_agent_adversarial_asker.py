#!/usr/bin/env python3
"""Adversarial asker against OpenCRE MCP ``ask`` (and completion fallbacks).

Does **not** load the synth suite. It probes the product contract: factual
OWASP chapter / project / leader / board / events / membership / AIX questions
that are knowable from public metadata should be answered — not refused with a
generic chapters/meetup clarify.

Modes (``OWASP_PROBE_COMPLETION_MODE``):
  mcp_ask     — persistent MCP stdio session calling tool ``ask``
                (default transport: registered staging MCP via ssh docker;
                or local ``python -m application.mcp`` with tunnel URL)
  mcp_inprocess — call ``application.mcp.ask.ask`` in-process
                (set ``OPENCRE_BASE_URL`` to the staging tunnel)
  http / inprocess — legacy ``/rest/v1/completion`` probes

Env:
  OWASP_PROBE_COMPLETION_MODE   default mcp_ask
  OWASP_ADV_MAX_TURNS           default 2000
  OWASP_ADV_OUT                 default tmp/owasp_agent_adversarial_failures.jsonl
  OWASP_ADV_SEED                optional int
  OWASP_ADV_MCP_TRANSPORT       staging_ssh (default) | local
  OPENCRE_BASE_URL              for local MCP / mcp_inprocess
                                (default http://127.0.0.1:15001)
  OWASP_AGENT_ENABLED           default 1
  OWASP_ADV_CORPUS              auto | owasp_meta | security (default auto)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO / "tmp" / "owasp_agent_adversarial_failures.jsonl"

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
    "what would you like to know",
    "what owasp metadata question",
)

GENERIC_WRONG_MARKERS = (
    "as an ai language model",
    "i cannot assist with that",
)

INFRA_MARKERS = (
    "__error__",
    "connection closed",
    "connection reset",
    "timed out",
    "timeout",
    "operationalerror",
    "internal server error",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
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
        ("Los Angeles", ("los angeles", "la ")),
        ("Amsterdam", ("amsterdam",)),
        ("Sydney", ("sydney",)),
        ("Toronto", ("toronto",)),
    ]
    projects = [
        ("ASVS", ("asvs", "application security verification")),
        ("Top Ten", ("top 10", "top ten")),
        ("Cheat Sheet Series", ("cheat sheet",)),
        ("Juice Shop", ("juice shop",)),
        ("Dependency-Check", ("dependency-check", "dependency check")),
        ("Amass", ("amass",)),
        ("API Security Top 10", ("api", "top 10", "top ten")),
        ("SAMM", ("samm", "software assurance")),
        ("CycloneDX", ("cyclonedx", "sbom")),
        ("AI Exchange", ("ai exchange", "ai security")),
    ]
    people = [
        ("Rob van der Veer", ("rob", "van der veer", "ai exchange")),
        ("Andrew van der Stock", ("andrew", "van der stock")),
        ("Sherif Mansour", ("sherif", "london")),
        ("OWASP board", ("board",)),
    ]
    cases: List[Case] = []

    for city, needles in chapters:
        cases.append(
            Case(
                q=f"Does OWASP have a chapter in {city}?",
                expect="must_any",
                needles=needles + ("chapter", "yes", "leaders", "meetup", "active"),
                note="chapter existence",
                cat="chapter_edge",
            )
        )
        cases.append(
            Case(
                q=f"What is the OWASP {city} chapter?",
                expect="must_any",
                needles=needles + ("chapter", "leader", "owasp"),
                note="chapter identity (what-is)",
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
        cases.append(
            Case(
                q=f"Tell me about the OWASP {name} project in one paragraph",
                expect="must_not_refuse",
                needles=(),
                note="project describe",
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
        Case(
            q="What does OWASP AI Exchange say about agentic AI risks?",
            expect="must_not_refuse",
            needles=(),
            note="aix agentic risks",
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
        Case(
            q="What are OWASP membership prices?",
            expect="must_not_refuse",
            needles=(),
            note="membership prices general",
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
        Case(
            q="Who was on the OWASP board in 2024?",
            expect="must_not_refuse",
            needles=(),
            note="board 2024",
            cat="board_edge",
        ),
    ]
    cases.extend(board)

    events = [
        Case(
            q="Are there OWASP events near London?",
            expect="must_not_refuse",
            needles=(),
            note="events near London",
            cat="events_edge",
        ),
        Case(
            q="Find OWASP meetups near Berlin",
            expect="must_not_refuse",
            needles=(),
            note="events near Berlin",
            cat="events_edge",
        ),
    ]
    cases.extend(events)

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
        Case(
            q="When is the next meetup?",
            expect="cre_ok",
            needles=(),
            note="ambiguous meetup — clarify ok",
            cat="trap_clarify",
        ),
    ]
    cases.extend(traps)

    extras: List[Case] = []
    for c in list(cases):
        if c.cat == "trap_clarify":
            continue
        variants = [
            f"Quick question: {c.q}",
            c.q.replace("?", " please?"),
            f"In one sentence: {c.q}",
            f"OWASP org: {c.q}",
            f"Fact check: {c.q}",
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


# --- completion HTTP / inprocess (legacy) ---------------------------------


def ask_http(q: str) -> str:
    url = os.environ.get(
        "OWASP_PROBE_COMPLETION_URL", "http://127.0.0.1:15001/rest/v1/completion"
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


_INPROCESS_APP = None


def ask_inprocess(q: str) -> str:
    global _INPROCESS_APP
    os.environ["NO_LOGIN"] = "1"
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")
    sys.path.insert(0, str(_REPO))
    if _INPROCESS_APP is None:
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

        _INPROCESS_APP = create_app(mode="production")
    app = _INPROCESS_APP
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


def ask_mcp_inprocess(q: str) -> str:
    """Call application.mcp.ask.ask locally (CRE via OPENCRE_BASE_URL)."""
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")
    os.environ.setdefault("OPENCRE_BASE_URL", "http://127.0.0.1:15001")
    sys.path.insert(0, str(_REPO))
    from application.mcp.ask import ask as run_ask

    corpus = (os.environ.get("OWASP_ADV_CORPUS") or "auto").strip()
    try:
        result = run_ask(q, corpus=corpus)
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__:{exc}"
    return _format_ask_result(result)


def _format_ask_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    if result.get("isError") or result.get("is_error"):
        return f"__ERROR__:{result}"
    msg = result.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg
    # Prefer owasp_agent message / clarify
    oa = result.get("owasp_agent") or {}
    if isinstance(oa, dict):
        clarify = oa.get("clarify")
        if clarify and not oa.get("ok"):
            return f"Answer: {clarify}"
    items = result.get("items")
    if items is not None:
        return json.dumps(
            {"ok": result.get("ok"), "items": items, "intent": result.get("intent")},
            ensure_ascii=False,
            default=str,
        )[:2000]
    return json.dumps(result, ensure_ascii=False, default=str)[:2000]


# --- MCP stdio (persistent) -----------------------------------------------


def _staging_ssh_params() -> Any:
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command="ssh",
        args=[
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=30",
            "sg@100.74.143.62",
            "docker",
            "exec",
            "-i",
            "-e",
            "OPENCRE_BASE_URL=http://127.0.0.1:5001",
            "-e",
            "PYTHONPATH=/code",
            "-e",
            "PYTHONUNBUFFERED=1",
            "-e",
            "OWASP_AGENT_ENABLED=1",
            "-e",
            f"OWASP_AGENT_LLM_PICK={os.environ.get('OWASP_AGENT_LLM_PICK') or '1'}",
            "-e",
            f"OWASP_AGENT_TOP_K={os.environ.get('OWASP_AGENT_TOP_K') or '8'}",
            "-w",
            "/code",
            "opencre-staging-web-1",
            "python",
            "-m",
            "application.mcp",
        ],
    )


def _local_mcp_params() -> Any:
    from mcp import StdioServerParameters

    base = os.environ.get("OPENCRE_BASE_URL") or "http://127.0.0.1:15001"
    python = str(_REPO / "venv" / "bin" / "python")
    if not Path(python).is_file():
        python = sys.executable
    env = {
        **os.environ,
        "OPENCRE_BASE_URL": base,
        "OWASP_AGENT_ENABLED": os.environ.get("OWASP_AGENT_ENABLED") or "1",
        "PYTHONPATH": str(_REPO),
        "PYTHONUNBUFFERED": "1",
    }
    if not (env.get("OWASP_AGENT_DB") or "").strip():
        sqlite = _REPO / "tmp" / "owasp_agent.sqlite"
        if sqlite.is_file():
            env["OWASP_AGENT_DB"] = str(sqlite)
    return StdioServerParameters(
        command=python,
        args=["-m", "application.mcp"],
        env=env,
        cwd=str(_REPO),
    )


class McpAskSession:
    """Reuse one MCP stdio connection across many ask calls."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._cm_stdio: Any = None
        self._cm_session: Any = None
        self._session: Any = None
        self._n = 0

    def start(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_async())

    async def _start_async(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        transport = (os.environ.get("OWASP_ADV_MCP_TRANSPORT") or "staging_ssh").strip()
        params = (
            _local_mcp_params() if transport == "local" else _staging_ssh_params()
        )
        self._cm_stdio = stdio_client(params)
        read, write = await self._cm_stdio.__aenter__()
        self._cm_session = ClientSession(read, write)
        self._session = await self._cm_session.__aenter__()
        await self._session.initialize()

    def ask(self, q: str) -> str:
        self._n += 1
        # Prefer fresh OS process batches over mid-session recycle (anyio cancel
        # scopes break when closing stdio_client from a sync wrapper).
        timeout = float(os.environ.get("OWASP_ADV_ASK_TIMEOUT") or "45")
        try:
            return self._loop.run_until_complete(
                asyncio.wait_for(self._ask_async(q), timeout=timeout)
            )
        except Exception as exc:  # noqa: BLE001
            return f"__ERROR__:mcp:{exc}"

    async def _ask_async(self, q: str) -> str:
        corpus = (os.environ.get("OWASP_ADV_CORPUS") or "auto").strip()
        result = await self._session.call_tool(
            "ask", {"prompt": q, "corpus": corpus}
        )
        if getattr(result, "isError", False):
            texts = []
            for c in result.content or []:
                texts.append(str(getattr(c, "text", c)))
            return f"__ERROR__:mcp_tool:{' '.join(texts)[:400]}"
        sc = getattr(result, "structuredContent", None) or getattr(
            result, "structured_content", None
        )
        if isinstance(sc, dict):
            return _format_ask_result(sc)
        for c in result.content or []:
            text = getattr(c, "text", None)
            if text:
                try:
                    return _format_ask_result(json.loads(text))
                except json.JSONDecodeError:
                    return str(text)
        return "__ERROR__:empty_mcp_result"

    def close(self) -> None:
        async def _close() -> None:
            if self._cm_session is not None:
                await self._cm_session.__aexit__(None, None, None)
            if self._cm_stdio is not None:
                await self._cm_stdio.__aexit__(None, None, None)

        try:
            if self._loop.is_running():
                return
            self._loop.run_until_complete(_close())
        except Exception:  # noqa: BLE001
            pass
        self._session = None
        self._cm_session = None
        self._cm_stdio = None


_MCP: Optional[McpAskSession] = None


def ask_mcp(q: str) -> str:
    global _MCP
    if _MCP is None:
        _MCP = McpAskSession()
        _MCP.start()
    return _MCP.ask(q)


def ask(q: str) -> str:
    mode = (os.environ.get("OWASP_PROBE_COMPLETION_MODE") or "mcp_ask").strip().lower()
    if mode == "mcp_ask":
        return ask_mcp(q)
    if mode in ("mcp_inprocess", "ask_inprocess"):
        return ask_mcp_inprocess(q)
    if mode == "inprocess":
        return ask_inprocess(q)
    return ask_http(q)


def is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    if not low.strip() or low.startswith("__error__"):
        return True
    return any(m in low for m in REFUSAL_MARKERS)


def is_infra(answer: str, reason: str) -> bool:
    blob = f"{answer} {reason}".lower()
    return any(m in blob for m in INFRA_MARKERS)


def judge(case: Case, answer: str) -> Tuple[bool, str]:
    """Return (ok, reason). ok=False means record as adversarial failure."""
    low = (answer or "").lower()
    if low.startswith("__error__"):
        return False, f"http_error:{answer[:120]}"
    if any(m in low for m in GENERIC_WRONG_MARKERS):
        return False, "generic_wrong"

    if case.expect == "cre_ok":
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
    infra = is_infra(answer, reason)
    row: Dict[str, Any] = {
        "id": 900000 + turn,
        "cat": f"adversarial_{case.cat}",
        "q": case.q,
        "path": "mcp_ask",
        "note": f"{case.note}; fail={reason}",
        "adversarial_answer_preview": (answer or "")[:400],
        "adversarial_reason": reason,
        "infra": infra,
        "substantive": not infra,
    }
    if case.expect == "must_any" and case.needles:
        row["must_any"] = list(case.needles)
    if case.expect == "must_not_refuse":
        row["must_not"] = [
            "which city are you in",
            "board history, and membership",
            "what would you like to know",
        ]
    return row


def _load_prior_failures(out_path: Path) -> List[Dict[str, Any]]:
    if not out_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in out_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> int:
    seed = int(os.environ.get("OWASP_ADV_SEED") or "14")
    rng = random.Random(seed)
    max_turns = int(os.environ.get("OWASP_ADV_MAX_TURNS") or "2000")
    start_turn = int(os.environ.get("OWASP_ADV_START_TURN") or "1")
    append = (os.environ.get("OWASP_ADV_APPEND") or "0").strip() == "1"
    out_path = Path(os.environ.get("OWASP_ADV_OUT") or str(_DEFAULT_OUT))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = (os.environ.get("OWASP_PROBE_COMPLETION_MODE") or "mcp_ask").strip().lower()
    os.environ.setdefault("OWASP_AGENT_ENABLED", "1")

    bank = _bank(rng)
    failures: List[Dict[str, Any]] = _load_prior_failures(out_path) if append else []
    ok_n = fail_n = infra_n = substantive_n = 0
    for r in failures:
        fail_n += 1
        if r.get("infra"):
            infra_n += 1
        else:
            substantive_n += 1
    print(
        json.dumps(
            {
                "start": True,
                "max_turns": max_turns,
                "start_turn": start_turn,
                "append": append,
                "bank": len(bank),
                "mode": mode,
                "mcp_transport": os.environ.get(
                    "OWASP_ADV_MCP_TRANSPORT", "staging_ssh"
                ),
                "base_url": os.environ.get("OPENCRE_BASE_URL"),
                "prior_fails": len(failures),
            }
        ),
        flush=True,
    )

    try:
        with out_path.open("a" if append else "w") as fh:
            for turn in range(start_turn, max_turns + 1):
                case = bank[(turn - 1) % len(bank)]
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
                    if row["infra"]:
                        infra_n += 1
                    else:
                        substantive_n += 1
                    failures.append(row)
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                    print(
                        f"FAIL turn={turn} {'infra' if row['infra'] else 'product'} "
                        f"{reason} | {q[:90]} || "
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
                                "infra": infra_n,
                                "substantive": substantive_n,
                                "last_dt": dt,
                            }
                        ),
                        flush=True,
                    )
    finally:
        global _MCP
        if _MCP is not None:
            try:
                _MCP.close()
            except Exception:  # noqa: BLE001
                pass
            _MCP = None

    summary_path = out_path.with_suffix(".summary.json")
    # Dedupe substantive fails by normalized question for promotion
    seen_q: set[str] = set()
    promote: List[Dict[str, Any]] = []
    for r in failures:
        if not r.get("substantive"):
            continue
        key = (r.get("q") or "").lower().strip()
        if key in seen_q:
            continue
        seen_q.add(key)
        promote.append(r)

    summary = {
        "turns": max_turns,
        "start_turn": start_turn,
        "ok_this_run": ok_n,
        "fail": fail_n,
        "infra": infra_n,
        "substantive": substantive_n,
        "unique_substantive": len(promote),
        "failures_path": str(out_path),
        "mode": mode,
        "failure_ids": [r["id"] for r in failures],
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    promote_path = out_path.with_suffix(".promote.jsonl")
    with promote_path.open("w") as pf:
        for r in promote:
            pf.write(json.dumps(r) + "\n")
    print("SUMMARY", json.dumps(summary), flush=True)
    print(f"PROMOTE {promote_path} n={len(promote)}", flush=True)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
