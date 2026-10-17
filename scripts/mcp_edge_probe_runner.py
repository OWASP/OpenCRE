#!/usr/bin/env python3
"""Incremental MCP edge-probe via staging Streamable HTTP + Cursor SDK.

Laptop-local only. Never uses ssh/docker MCP stdio.

Flow per turn:
  Cursor agent generates question → write question to disk →
  Python calls staging ``ask`` over HTTPS → write answer →
  same Cursor agent evaluates → write eval.

Classifications (every turn):
  mcp_ok | mcp_fail
  answer_good | answer_bad   (only when mcp_ok; product quality)

Stop when cumulative_product_bad > 100, or after tier 5000.
Default: record mcp_fail and continue. Optional consecutive stop:
  MCP_EDGE_PROBE_MCP_FAIL_STOP=N  (0 = disabled)

Env:
  CURSOR_API_KEY                     required (unless --dry-run)
  OPENCRE_STAGING_ADMIN_API_TOKEN    Bearer for remote ask
  MCP_EDGE_PROBE_URL                 default https://staging.opencre.org/mcp
  MCP_EDGE_PROBE_SEED_JSONL          default tmp/owasp_mcp_ask_adv_5k_questions.jsonl
  MCP_EDGE_PROBE_OUT                 default tmp/mcp_edge_probe
  MCP_EDGE_PROBE_MODEL               default composer-2.5
  MCP_EDGE_PROBE_CORPUS              default auto
  MCP_EDGE_PROBE_MCP_FAIL_STOP       consecutive mcp_fail stop (default 0)
  MCP_EDGE_PROBE_TIERS               comma list (default 10,100,500,1000,2000,3000,4000,5000)
  MCP_EDGE_PROBE_LOCAL_ASK=1         call application.mcp.ask in-process (seeded local DB)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_SEED = _REPO / "tmp" / "owasp_mcp_ask_adv_5k_questions.jsonl"
_DEFAULT_OUT = _REPO / "tmp" / "mcp_edge_probe"
_TIERS_DEFAULT = (10, 100, 500, 1000, 2000, 3000, 4000, 5000)
_PRODUCT_BAD_STOP = 100

# Forced starter families — structural/count traps the old LIKE path missed.
_FORCED_SEEDS: List[Dict[str, Any]] = [
    {
        "family": "asvs_levels",
        "q": "How many levels does OWASP ASVS have?",
        "note": "structural count trap",
    },
    {
        "family": "masvs_levels",
        "q": "How many levels / verification levels does OWASP MASVS define?",
        "note": "structural count trap",
    },
    {
        "family": "samm_levels",
        "q": "How many maturity levels does OWASP SAMM use?",
        "note": "structural count trap",
    },
    {
        "family": "aix_layers",
        "q": "How many layers are in the OWASP AI Exchange (AIX) model?",
        "note": "AIX site structural fact",
    },
    {
        "family": "aix_layers",
        "q": "What are the 7 layers of the OWASP AI Exchange?",
        "note": "AIX layers list",
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(f"[{_utc()}] {msg}", flush=True)


def _loud_mcp_fail(turn: int, detail: Dict[str, Any]) -> None:
    bar = "=" * 72
    print(bar, flush=True)
    print(f"MCP_FAIL turn={turn}", flush=True)
    print(json.dumps(detail, indent=2, default=str)[:4000], flush=True)
    print(bar, flush=True)


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


def _load_seed_starters(path: Path, per_family: int = 2) -> List[Dict[str, Any]]:
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cat = str(row.get("cat") or "unknown")
            if len(by_cat[cat]) < per_family:
                by_cat[cat].append(
                    {
                        "family": cat,
                        "q": row.get("q"),
                        "expect": row.get("expect"),
                        "needles": row.get("needles"),
                        "note": row.get("note"),
                        "seed_turn": row.get("turn"),
                        "source": "frozen_jsonl",
                    }
                )
    starters = list(_FORCED_SEEDS)
    for cat in sorted(by_cat):
        starters.extend(by_cat[cat])
    return starters


class EdgeProbeRun:
    def __init__(
        self,
        *,
        out_root: Path,
        seed_jsonl: Path,
        mcp_url: str,
        token: str,
        model: str,
        corpus: str,
        tiers: Tuple[int, ...],
        mcp_fail_stop: int,
        dry_run: bool,
    ) -> None:
        self.out_root = out_root
        self.seed_jsonl = seed_jsonl
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        self.model = model
        self.corpus = corpus
        self.tiers = tiers
        self.mcp_fail_stop = mcp_fail_stop
        self.dry_run = dry_run

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = out_root / f"run_{run_id}"
        self.q_dir = self.run_dir / "questions"
        self.a_dir = self.run_dir / "answers"
        self.e_dir = self.run_dir / "evals"
        self.mcp_fail_dir = self.run_dir / "mcp_fails"
        for d in (
            self.run_dir,
            self.q_dir,
            self.a_dir,
            self.e_dir,
            self.mcp_fail_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self.mutations_path = self.run_dir / "mutations.jsonl"
        self.results_path = self.run_dir / "all_results.jsonl"
        self.state_path = self.run_dir / "state.json"
        self.summary_path = self.run_dir / "summary.json"
        self.seed_path = self.run_dir / "seed_families.json"
        self.pid_path = out_root / "runner.pid"
        self.latest_path = out_root / "latest_run"

        self.starters = _load_seed_starters(seed_jsonl)
        self.seed_path.write_text(
            json.dumps({"starters": self.starters}, indent=2), encoding="utf-8"
        )

        self.agent: Any = None
        self.agent_id: Optional[str] = None
        self.turn = 0
        self.cumulative_product_bad = 0
        self.mcp_fail_count = 0
        self.consecutive_mcp_fail = 0
        self.answer_good_count = 0
        self.mcp_ok_count = 0
        self.family_bad: Counter[str] = Counter()
        self.family_good: Counter[str] = Counter()
        self.tier_stats: Dict[str, Dict[str, int]] = {}
        self._starter_i = 0

        self.latest_path.write_text(str(self.run_dir), encoding="utf-8")
        self.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    def _write_state(self, **extra: Any) -> None:
        payload = {
            "updated_at": _utc(),
            "run_dir": str(self.run_dir),
            "pid": os.getpid(),
            "agent_id": self.agent_id,
            "turn": self.turn,
            "tiers": list(self.tiers),
            "cumulative_product_bad": self.cumulative_product_bad,
            "mcp_fail_count": self.mcp_fail_count,
            "consecutive_mcp_fail": self.consecutive_mcp_fail,
            "answer_good_count": self.answer_good_count,
            "mcp_ok_count": self.mcp_ok_count,
            "product_bad_stop": _PRODUCT_BAD_STOP,
            "mcp_fail_stop": self.mcp_fail_stop,
            "tier_stats": self.tier_stats,
            **extra,
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_jsonl(self, path: Path, row: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _agent_text(self, prompt: str) -> str:
        if self.dry_run:
            return ""
        assert self.agent is not None
        run = self.agent.send(prompt)
        result = run.wait()
        if getattr(result, "status", None) == "error":
            raise RuntimeError(f"cursor run error: {getattr(result, 'id', '?')}")
        # Prefer convenience helper when present
        if hasattr(run, "text"):
            try:
                return str(run.text() or "")
            except Exception:
                pass
        parts: List[str] = []
        try:
            for message in run.messages():
                if getattr(message, "type", None) != "assistant":
                    continue
                content = getattr(getattr(message, "message", None), "content", None)
                if not content:
                    continue
                for block in content:
                    if getattr(block, "type", None) == "text":
                        parts.append(str(getattr(block, "text", "") or ""))
        except Exception:
            pass
        return "\n".join(parts).strip()

    def _director_context(self, tier: int, tier_target: int) -> str:
        failing = [f"{k}:{v}" for k, v in self.family_bad.most_common(12)]
        succeeding = [f"{k}:{v}" for k, v in self.family_good.most_common(12)]
        return (
            "You are generating adversarial OpenCRE MCP `ask` probes.\n"
            "Goal: find edge cases where staging ask returns a BAD answer "
            "(wrong, empty, refuse, or missing structural facts).\n"
            "Prioritize structural/count traps: ASVS levels, MASVS levels, "
            "SAMM maturity levels, OWASP AI Exchange (AIX) layers (often 7), "
            "and similar 'how many X' questions that keyword-LIKE retrieval misses.\n"
            "Also mutate chapter/project/person/membership families toward typos, "
            "aliases, negation, multilingual, and multi-hop traps.\n"
            f"Tier={tier} progress_in_tier≈{self.turn}/{tier_target} "
            f"cumulative_product_bad={self.cumulative_product_bad} "
            f"mcp_fail_count={self.mcp_fail_count}.\n"
            f"Failing families to EXPAND: {failing or ['(none yet)']}\n"
            f"Success families to AVOID or invert: {succeeding or ['(none yet)']}\n"
        )

    def _generate_question(self, tier: int, tier_target: int) -> Dict[str, Any]:
        # First pass: drain forced/frozen starters before Cursor mutations.
        if self._starter_i < len(self.starters):
            seed = self.starters[self._starter_i]
            self._starter_i += 1
            q = {
                "family": seed.get("family") or "seed",
                "q": seed["q"],
                "note": seed.get("note"),
                "parent_q": seed.get("q"),
                "mutation": "seed",
                "source": seed.get("source", "forced"),
            }
            return q

        if self.dry_run:
            fam = "dry_asvs"
            return {
                "family": fam,
                "q": f"[dry-run] How many ASVS levels? turn={self.turn+1}",
                "note": "dry-run",
                "parent_q": None,
                "mutation": "dry",
                "source": "dry_run",
            }

        prompt = (
            self._director_context(tier, tier_target) + "\nReturn ONLY JSON with keys: "
            "family (string), q (string question), note (string), "
            "parent_q (string|null), mutation (short tag).\n"
            "Make q harder than previous successes; expand failing families.\n"
        )
        raw = self._agent_text(prompt)
        data = _parse_json_blob(raw)
        qtext = str(data.get("q") or "").strip()
        if not qtext:
            qtext = "How many levels does OWASP ASVS have?"
            data = {
                "family": "asvs_levels",
                "q": qtext,
                "note": "fallback after empty agent json",
                "parent_q": None,
                "mutation": "fallback",
            }
        data["q"] = qtext
        data.setdefault("family", "unknown")
        data.setdefault("mutation", "agent")
        data["source"] = "cursor_agent"
        data["agent_raw"] = raw[:4000]
        return data

    async def _mcp_ask(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        """Return (status, payload). status is mcp_ok or mcp_fail."""
        if self.dry_run:
            return "mcp_ok", {
                "ok": True,
                "channel": "dry_run",
                "message": f"dry-run echo: {prompt[:200]}",
                "items": [],
            }

        if (os.environ.get("MCP_EDGE_PROBE_LOCAL_ASK") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return await asyncio.to_thread(self._local_ask, prompt)

        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        # MCP SDK RequestClock expects float seconds, not datetime.timedelta.
        _ask_timeout_s = 90.0

        headers = {"Authorization": f"Bearer {self.token}"}
        http = create_mcp_http_client(headers=headers)
        try:
            async with streamable_http_client(
                self.mcp_url, http_client=http, terminate_on_close=True
            ) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "ask",
                        {"prompt": prompt, "corpus": self.corpus},
                        read_timeout_seconds=_ask_timeout_s,
                    )
                    if getattr(result, "isError", None):
                        texts = []
                        for c in getattr(result, "content", None) or []:
                            texts.append(getattr(c, "text", None) or str(c))
                        return "mcp_fail", {
                            "error": "tool_isError",
                            "status": None,
                            "body": "\n".join(str(t) for t in texts)[:8000],
                        }
                    sc = getattr(result, "structuredContent", None) or getattr(
                        result, "structured_content", None
                    )
                    if isinstance(sc, dict):
                        return "mcp_ok", sc
                    # Fallback: parse text content
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
            # ExceptionGroup/TaskGroup hides the root cause in str(exc); unwrap.
            body = str(exc)
            sub = getattr(exc, "exceptions", None)
            if sub:
                parts = [f"{type(e).__name__}: {e}" for e in sub[:5]]
                body = "; ".join(parts) or body
            return "mcp_fail", {
                "error": type(exc).__name__,
                "status": getattr(exc, "status", None)
                or getattr(exc, "status_code", None),
                "body": body[:8000],
                "traceback": traceback.format_exc()[-6000:],
            }
        finally:
            try:
                await http.aclose()
            except Exception:
                pass

    def _local_ask(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        """In-process ask against the local Flask/DB (for post-seed probes)."""
        try:
            from application import create_app
            from application.mcp.ask import ask

            app = create_app(mode="production")
            with app.app_context():
                payload = ask(prompt, corpus=self.corpus)
            if isinstance(payload, dict):
                return "mcp_ok", payload
            return "mcp_fail", {
                "error": "non_dict_payload",
                "body": str(payload)[:4000],
            }
        except Exception as exc:
            return "mcp_fail", {
                "error": type(exc).__name__,
                "body": str(exc)[:8000],
                "traceback": traceback.format_exc()[-6000:],
            }

    def _eval_answer(
        self, question: Dict[str, Any], answer: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self.dry_run:
            # Alternate good/bad for dry-run visibility
            bad = (self.turn % 7) == 0
            return {
                "verdict": "answer_bad" if bad else "answer_good",
                "reason": "dry-run alternating verdict",
                "confidence": 0.5,
            }

        prompt = (
            "You evaluate OpenCRE MCP `ask` answers for factual adequacy.\n"
            "Question JSON:\n"
            f"{json.dumps(question, ensure_ascii=False)[:3000]}\n\n"
            "Answer JSON from MCP ask:\n"
            f"{json.dumps(answer, ensure_ascii=False)[:6000]}\n\n"
            "Return ONLY JSON with keys:\n"
            '  verdict: "answer_good" | "answer_bad"\n'
            "  reason: short string\n"
            "  confidence: 0..1\n"
            "Mark answer_bad if wrong, empty, refuse, off-topic, or missing "
            "the structural fact the question asked (counts/levels/layers).\n"
            "Infra/transport errors are NOT your job (already classified).\n"
        )
        raw = self._agent_text(prompt)
        data = _parse_json_blob(raw)
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in ("answer_good", "answer_bad"):
            # Heuristic fallback
            msg = json.dumps(answer).lower()
            if not answer or answer.get("ok") is False:
                verdict = "answer_bad"
            elif "i don't" in msg or "not sure" in msg:
                verdict = "answer_bad"
            else:
                verdict = "answer_good"
            data["verdict"] = verdict
            data.setdefault("reason", "normalized from agent output")
        data["agent_raw"] = raw[:4000]
        return data

    def _one_turn(self, tier: int, tier_target: int) -> Dict[str, Any]:
        self.turn += 1
        turn = self.turn
        question = self._generate_question(tier, tier_target)
        family = str(question.get("family") or "unknown")

        q_path = self.q_dir / f"{turn:05d}.json"
        q_row = {
            "turn": turn,
            "tier": tier,
            "tier_target": tier_target,
            "ts": _utc(),
            **question,
        }
        q_path.write_text(json.dumps(q_row, indent=2), encoding="utf-8")
        if question.get("parent_q") and question.get("mutation") not in (
            "seed",
            None,
        ):
            self._append_jsonl(
                self.mutations_path,
                {
                    "turn": turn,
                    "family": family,
                    "old_q": question.get("parent_q"),
                    "new_q": question.get("q"),
                    "mutation": question.get("mutation"),
                },
            )

        # MCP only after question is on disk
        mcp_status, mcp_body = asyncio.run(self._mcp_ask(str(question["q"])))
        a_path = self.a_dir / f"{turn:05d}.json"
        a_row = {
            "turn": turn,
            "tier": tier,
            "ts": _utc(),
            "mcp_status": mcp_status,
            "prompt": question.get("q"),
            "response": mcp_body,
        }
        a_path.write_text(json.dumps(a_row, indent=2, default=str), encoding="utf-8")

        answer_verdict: Optional[str] = None
        eval_row: Optional[Dict[str, Any]] = None
        if mcp_status == "mcp_fail":
            self.mcp_fail_count += 1
            self.consecutive_mcp_fail += 1
            fail_path = self.mcp_fail_dir / f"{turn:05d}.json"
            fail_detail = {
                "turn": turn,
                "tier": tier,
                "ts": _utc(),
                "question_path": str(q_path),
                "prompt": question.get("q"),
                "error": mcp_body.get("error"),
                "status": mcp_body.get("status"),
                "body": mcp_body.get("body") or mcp_body,
                "mcp_url": self.mcp_url,
            }
            fail_path.write_text(
                json.dumps(fail_detail, indent=2, default=str), encoding="utf-8"
            )
            _loud_mcp_fail(turn, fail_detail)
        else:
            self.mcp_ok_count += 1
            self.consecutive_mcp_fail = 0
            eval_row = self._eval_answer(question, mcp_body)
            answer_verdict = str(eval_row.get("verdict") or "answer_bad")
            e_path = self.e_dir / f"{turn:05d}.json"
            e_path.write_text(
                json.dumps(
                    {"turn": turn, "tier": tier, "ts": _utc(), **eval_row},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            if answer_verdict == "answer_bad":
                self.cumulative_product_bad += 1
                self.family_bad[family] += 1
            else:
                self.answer_good_count += 1
                self.family_good[family] += 1

        result = {
            "turn": turn,
            "tier": tier,
            "tier_target": tier_target,
            "ts": _utc(),
            "family": family,
            "q": question.get("q"),
            "mcp_status": mcp_status,
            "answer_verdict": answer_verdict,
            "cumulative_product_bad": self.cumulative_product_bad,
            "mcp_fail_count": self.mcp_fail_count,
            "question_path": str(q_path),
            "answer_path": str(a_path),
        }
        self._append_jsonl(self.results_path, result)
        self._write_state(current_tier=tier, tier_target=tier_target)
        _log(
            f"turn={turn} tier={tier} mcp={mcp_status} "
            f"verdict={answer_verdict} product_bad={self.cumulative_product_bad} "
            f"mcp_fail={self.mcp_fail_count} | {(question.get('q') or '')[:80]}"
        )
        return result

    def run(self) -> int:
        from cursor_sdk import Agent, LocalAgentOptions

        api_key = os.environ.get("CURSOR_API_KEY") or ""
        if not self.dry_run and not api_key:
            _log("ERROR: CURSOR_API_KEY required (or pass --dry-run)")
            return 2
        local_ask = (
            os.environ.get("MCP_EDGE_PROBE_LOCAL_ASK") or ""
        ).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not self.dry_run and not self.token and not local_ask:
            _log("ERROR: OPENCRE_STAGING_ADMIN_API_TOKEN required for remote ask")
            return 2

        stop_reason = "completed_all_tiers"
        try:
            if self.dry_run:
                self.agent = None
                self.agent_id = "dry-run"
            else:
                self.agent = Agent.create(
                    model=self.model,
                    api_key=api_key,
                    name="opencre-mcp-edge-probe",
                    local=LocalAgentOptions(cwd=str(_REPO)),
                )
                self.agent_id = getattr(self.agent, "agent_id", None) or getattr(
                    self.agent, "id", None
                )
                _log(f"cursor agent id={self.agent_id}")

            for tier in self.tiers:
                tier_key = str(tier)
                self.tier_stats[tier_key] = {
                    "target": tier,
                    "turns": 0,
                    "mcp_ok": 0,
                    "mcp_fail": 0,
                    "answer_good": 0,
                    "answer_bad": 0,
                }
                _log(f"=== TIER {tier} start (global_turn={self.turn}) ===")
                while self.turn < tier:
                    row = self._one_turn(tier, tier)
                    st = self.tier_stats[tier_key]
                    st["turns"] += 1
                    if row["mcp_status"] == "mcp_fail":
                        st["mcp_fail"] += 1
                    else:
                        st["mcp_ok"] += 1
                        if row["answer_verdict"] == "answer_bad":
                            st["answer_bad"] += 1
                        else:
                            st["answer_good"] += 1

                    if self.cumulative_product_bad > _PRODUCT_BAD_STOP:
                        stop_reason = f"product_bad_stop>{_PRODUCT_BAD_STOP}"
                        _log(stop_reason)
                        break
                    if (
                        self.mcp_fail_stop > 0
                        and self.consecutive_mcp_fail >= self.mcp_fail_stop
                    ):
                        stop_reason = f"mcp_fail_consecutive>={self.mcp_fail_stop}"
                        _log(stop_reason)
                        break
                self._write_summary(stop_reason)
                if stop_reason != "completed_all_tiers" and not stop_reason.startswith(
                    "completed"
                ):
                    if "stop" in stop_reason:
                        break
            else:
                stop_reason = "completed_all_tiers"
        finally:
            if self.agent is not None:
                try:
                    self.agent.close()
                except Exception:
                    pass
            self._write_summary(stop_reason)
            _log(f"DONE reason={stop_reason} summary={self.summary_path}")

        return 0 if stop_reason.startswith("completed") else 1

    def _write_summary(self, stop_reason: str) -> None:
        summary = {
            "finished_at": _utc(),
            "stop_reason": stop_reason,
            "run_dir": str(self.run_dir),
            "agent_id": self.agent_id,
            "turns": self.turn,
            "mcp_ok_count": self.mcp_ok_count,
            "mcp_fail_count": self.mcp_fail_count,
            "answer_good_count": self.answer_good_count,
            "cumulative_product_bad": self.cumulative_product_bad,
            "product_bad_stop": _PRODUCT_BAD_STOP,
            "mcp_fail_stop": self.mcp_fail_stop,
            "tier_stats": self.tier_stats,
            "failing_families": self.family_bad.most_common(30),
            "success_families": self.family_good.most_common(30),
            "mcp_url": self.mcp_url,
        }
        self.summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        self._write_state(stop_reason=stop_reason)


def _parse_tiers(raw: str) -> Tuple[int, ...]:
    parts = [int(x.strip()) for x in raw.split(",") if x.strip()]
    if not parts:
        return _TIERS_DEFAULT
    return tuple(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--tiers",
        default=os.environ.get(
            "MCP_EDGE_PROBE_TIERS", ",".join(str(t) for t in _TIERS_DEFAULT)
        ),
    )
    args = ap.parse_args()
    out = Path(os.environ.get("MCP_EDGE_PROBE_OUT") or _DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)
    runner = EdgeProbeRun(
        out_root=out,
        seed_jsonl=Path(os.environ.get("MCP_EDGE_PROBE_SEED_JSONL") or _DEFAULT_SEED),
        mcp_url=os.environ.get("MCP_EDGE_PROBE_URL", "https://staging.opencre.org/mcp"),
        token=(os.environ.get("OPENCRE_STAGING_ADMIN_API_TOKEN") or "").strip(),
        model=os.environ.get("MCP_EDGE_PROBE_MODEL") or "composer-2.5",
        corpus=(os.environ.get("MCP_EDGE_PROBE_CORPUS") or "auto").strip(),
        tiers=_parse_tiers(args.tiers),
        mcp_fail_stop=int(os.environ.get("MCP_EDGE_PROBE_MCP_FAIL_STOP") or "0"),
        dry_run=bool(args.dry_run),
    )
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
