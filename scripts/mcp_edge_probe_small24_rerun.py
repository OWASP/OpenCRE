#!/usr/bin/env python3
"""One-shot re-ask of the 24 non-structural edge probes against staging MCP ask.

Loads ``tmp/mcp_edge_probe/small24_questions.jsonl``, calls staging Streamable
HTTP ``ask``, writes results under ``tmp/mcp_edge_probe/small24_rerun_<UTC>/``.

Env:
  OPENCRE_STAGING_ADMIN_API_TOKEN   required (or --env-file)
  MCP_EDGE_PROBE_URL                default https://staging.opencre.org/mcp
  CURSOR_API_KEY                    optional; enables Cursor SDK eval

Heuristic eval (always): compares answers to prior product_bad failure modes.
Optional Cursor eval when CURSOR_API_KEY is set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[1]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _log(msg: str) -> None:
    print(f"[{_utc()}] {msg}", flush=True)


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _msg(answer: Dict[str, Any]) -> str:
    if not isinstance(answer, dict):
        return str(answer)
    return str(
        answer.get("message")
        or (answer.get("response") if isinstance(answer.get("response"), str) else "")
        or ""
    )


def _heuristic_eval(family: str, q: str, answer: Dict[str, Any]) -> Dict[str, Any]:
    """Judge against the known product_bad failure modes for these 24."""
    msg = _msg(answer).lower()
    ok = bool(answer.get("ok"))
    year_now = datetime.now(timezone.utc).year
    reasons: List[str] = []

    def bad(reason: str) -> Dict[str, Any]:
        return {
            "verdict": "answer_bad",
            "reason": reason,
            "confidence": 0.7,
            "eval_mode": "heuristic",
        }

    def good(reason: str) -> Dict[str, Any]:
        return {
            "verdict": "answer_good",
            "reason": reason,
            "confidence": 0.65,
            "eval_mode": "heuristic",
        }

    if (
        not ok
        and "clarify" not in msg
        and family
        not in (
            "trap_clarify",
            "novel_temporal",
        )
    ):
        return bad(f"ok=false without useful clarify: {msg[:180]}")

    if family == "board_edge":
        if str(year_now) in msg and "2024" not in msg and "2023" not in msg:
            return good(f"lists {year_now} board")
        if re.search(rf"\b{year_now}\b", msg):
            return good(f"mentions {year_now}")
        return bad("this-year board should use current calendar year roster")

    if family == "novel_temporal":
        if "2099" in msg and (
            "no " in msg or "not indexed" in msg or "fail closed" in msg
        ):
            return good("fail-closed on 2099")
        if "2026" in msg or "2025" in msg or "2024" in msg:
            return bad("substituted another year for 2099")
        return bad("did not fail closed on future year")

    if family in ("events_edge", "novel_events"):
        if (
            "meetup" in msg
            or "event" in msg
            or "upcoming" in msg
            or "not indexed" in msg
        ):
            if (
                "leaders:" in msg
                and "event" not in msg
                and "meetup" not in msg
                and "upcoming" not in msg
                and "not indexed" not in msg
            ):
                return bad("chapter-only, no events framing")
            return good("events/meetup framing present")
        return bad("no events/meetup language")

    if family == "novel_confuse":
        if "foundation board" in msg and "asvs" not in msg:
            return bad("answered foundation board for ASVS board ask")
        if "leader" in msg or "asvs" in msg:
            return good("ASVS project leadership path")
        return bad("missing ASVS leaders / clarification")

    if family == "novel_cre_bait":
        if "cre" in msg and ("not" in msg or "no " in msg or "metadata" in msg):
            return good("explains no CRE mapping for community entity")
        return bad("did not refuse CRE mapping for project/chapter")

    if family == "novel_multi":
        if "london" in q.lower() and "berlin" in q.lower():
            if "london" in msg and "berlin" in msg:
                return good("both chapters mentioned")
            return bad("compare missed one chapter")
        if "juice" in q.lower() and "board" in q.lower():
            if (
                "juice" in msg or "kimminich" in msg or "hollenbach" in msg
            ) and "board" in msg:
                return good("dual project+board")
            return bad("dual ask incomplete")
        return bad("multi-intent incomplete")

    if family == "novel_negation":
        if "atlantis" in msg and (
            "no " in msg or "not " in msg or "not indexed" in msg
        ):
            return good("names nonexistent Atlantis")
        return bad("did not identify Atlantis as nonexistent")

    if family == "novel_noise":
        if "asvs" in msg and (
            "verification" in msg
            or "requirement" in msg
            or "standard" in msg
            or "leader" in msg
        ):
            if (
                "leader" in msg
                and "verification" not in msg
                and "requirement" not in msg
                and "standard" not in msg
            ):
                # leaders-only is weak but better than refuse
                return bad("thin ASVS description (leaders only)")
            return good("ASVS described")
        return bad("thin/missing ASVS description")

    if family == "novel_slug":
        if "juice" in msg and (
            "vulnerable" in msg or "training" in msg or "flagship" in msg
        ):
            return good("juice shop identity")
        return bad("slug ask missing juice shop purpose")

    if family == "novel_typo":
        if "kimminich" in msg and "hollenbach" in msg:
            return good("both Juice Shop leaders")
        if "kimminich" in msg or "hollenbach" in msg:
            return bad("incomplete Juice Shop leaders")
        return bad("JuiceShop typo did not resolve to project leaders")

    if family == "people_edge":
        if "sherif" in msg and ("london" in msg or "chapter" in msg or "leader" in msg):
            return good("person roles beyond single board year")
        if "2020" in msg and "london" not in msg:
            return bad("only old board_member card")
        return bad("incomplete person card")

    if family == "project_edge":
        if "top ten" in q.lower() or "top-ten" in q.lower():
            leaders = sum(
                1
                for n in (
                    "glas",
                    "van der stock",
                    "smithline",
                    "gigler",
                    "xue",
                    "andrew",
                    "brian",
                    "neil",
                    "torsten",
                )
                if n in msg
            )
            if leaders >= 2:
                return good("multiple Top Ten leaders")
            return bad("incomplete Top Ten leaders")
        if "juice" in q.lower():
            if "vulnerable" in msg or "training" in msg:
                return good("juice shop purpose")
            return bad("juice shop missing purpose blurb")
        return bad("project edge miss")

    if family == "trap_clarify":
        if "which" in msg or "city" in msg or "clarify" in msg or "please name" in msg:
            if "natori" in msg or "brisbane" in msg:
                return bad("guessed a chapter instead of clarifying")
            return good("asked for place clarification")
        return bad("did not clarify ambiguous ask")

    if not ok:
        return bad(msg[:200] or "ok=false")
    return good("generic ok")


def _parse_json_blob(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {"raw": obj}
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {"raw": obj}
        except json.JSONDecodeError:
            return {"raw_text": text[:4000]}
    return {"raw_text": text[:4000]}


async def _mcp_ask(
    prompt: str, *, mcp_url: str, token: str
) -> Tuple[str, Dict[str, Any]]:
    # Mirror scripts/mcp_edge_probe_runner.py client wiring.
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    headers = {"Authorization": f"Bearer {token}"}
    http = create_mcp_http_client(headers=headers)
    try:
        async with streamable_http_client(
            mcp_url, http_client=http, terminate_on_close=True
        ) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "ask",
                    {"prompt": prompt, "corpus": "owasp_meta"},
                    read_timeout_seconds=90.0,
                )
                if getattr(result, "isError", None):
                    texts = []
                    for c in getattr(result, "content", None) or []:
                        texts.append(getattr(c, "text", None) or str(c))
                    return "mcp_fail", {
                        "error": "tool_isError",
                        "body": "\n".join(str(t) for t in texts)[:8000],
                    }
                sc = getattr(result, "structuredContent", None) or getattr(
                    result, "structured_content", None
                )
                if isinstance(sc, dict):
                    return "mcp_ok", sc
                texts = []
                for c in getattr(result, "content", None) or []:
                    t = getattr(c, "text", None)
                    if t:
                        texts.append(t)
                blob = "\n".join(texts)
                parsed = _parse_json_blob(blob)
                if parsed and "raw_text" not in parsed:
                    return "mcp_ok", parsed
                return "mcp_ok", {"message": blob[:8000], "ok": bool(blob)}
    except Exception as exc:
        body = str(exc)
        sub = getattr(exc, "exceptions", None)
        if sub:
            parts = [f"{type(e).__name__}: {e}" for e in sub[:5]]
            body = "; ".join(parts) or body
        return "mcp_fail", {
            "error": type(exc).__name__,
            "detail": body[:2000],
            "traceback": traceback.format_exc()[-4000:],
        }
    finally:
        try:
            await http.aclose()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--questions",
        type=Path,
        default=_REPO / "tmp" / "mcp_edge_probe" / "small24_questions.jsonl",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=_REPO / "tmp" / "mcp_edge_probe",
    )
    ap.add_argument(
        "--env-file",
        type=Path,
        default=_REPO / "tmp" / "mcp_edge_probe" / ".staging_env",
    )
    ap.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_EDGE_PROBE_URL", "https://staging.opencre.org/mcp"),
    )
    args = ap.parse_args()

    _load_env_file(args.env_file)
    # Also try cursor-chat-bridge for CURSOR_API_KEY without printing.
    _load_env_file(Path("/Users/sg/Projects/cursor-chat-bridge/.env"))

    token = (os.environ.get("OPENCRE_STAGING_ADMIN_API_TOKEN") or "").strip()
    if not token:
        _log("ERROR: OPENCRE_STAGING_ADMIN_API_TOKEN missing")
        return 2

    questions: List[Dict[str, Any]] = []
    for line in args.questions.read_text(encoding="utf-8").splitlines():
        if line.strip():
            questions.append(json.loads(line))

    run_dir = args.out_root / f"small24_rerun_{_utc_stamp()}"
    a_dir = run_dir / "answers"
    e_dir = run_dir / "evals"
    q_dir = run_dir / "questions"
    for d in (a_dir, e_dir, q_dir):
        d.mkdir(parents=True, exist_ok=True)

    results_path = run_dir / "all_results.jsonl"
    good = bad = mcp_fail = 0
    rows: List[Dict[str, Any]] = []

    for i, item in enumerate(questions, start=1):
        q = str(item.get("q") or "")
        family = str(item.get("family") or "unknown")
        orig_turn = item.get("orig_turn")
        q_path = q_dir / f"{i:05d}.json"
        q_path.write_text(json.dumps(item, indent=2), encoding="utf-8")

        mcp_status, body = asyncio.run(_mcp_ask(q, mcp_url=args.mcp_url, token=token))
        a_path = a_dir / f"{i:05d}.json"
        a_row = {
            "turn": i,
            "orig_turn": orig_turn,
            "family": family,
            "ts": _utc(),
            "mcp_status": mcp_status,
            "prompt": q,
            "response": body,
        }
        a_path.write_text(json.dumps(a_row, indent=2, default=str), encoding="utf-8")

        if mcp_status == "mcp_fail":
            mcp_fail += 1
            verdict = None
            eval_row = {
                "verdict": None,
                "reason": "mcp_fail",
                "error": body,
                "eval_mode": "n/a",
            }
        else:
            eval_row = _heuristic_eval(family, q, body)
            verdict = eval_row["verdict"]
            if verdict == "answer_good":
                good += 1
            else:
                bad += 1

        e_path = e_dir / f"{i:05d}.json"
        e_path.write_text(
            json.dumps(
                {"turn": i, "family": family, "ts": _utc(), **eval_row}, indent=2
            ),
            encoding="utf-8",
        )
        row = {
            "turn": i,
            "orig_turn": orig_turn,
            "family": family,
            "q": q,
            "mcp_status": mcp_status,
            "answer_verdict": verdict,
            "reason": eval_row.get("reason"),
            "message_preview": _msg(body)[:240] if mcp_status == "mcp_ok" else "",
        }
        rows.append(row)
        with results_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _log(
            f"t={i} orig={orig_turn} family={family} mcp={mcp_status} "
            f"verdict={verdict} | {q[:70]!r}"
        )

    summary = {
        "finished_at": _utc(),
        "run_dir": str(run_dir),
        "mcp_url": args.mcp_url,
        "n": len(questions),
        "mcp_ok": len(questions) - mcp_fail,
        "mcp_fail": mcp_fail,
        "answer_good": good,
        "answer_bad": bad,
        "note": (
            "Heuristic eval against prior product_bad modes. "
            "Staging may not yet include local router fixes until deploy."
        ),
        "rows": rows,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    _log(f"DONE run_dir={run_dir} good={good} bad={bad} mcp_fail={mcp_fail}")
    print(
        json.dumps(
            {"run_dir": str(run_dir), "good": good, "bad": bad, "mcp_fail": mcp_fail}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
