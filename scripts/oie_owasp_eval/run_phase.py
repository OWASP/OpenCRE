#!/usr/bin/env python3
"""Unattended OIE OWASP eval — advance one phase per invocation.

Phases write JSON artifacts under tmp/oie_owasp_eval/ for the agent loop / canvas.
Does not commit. Loads GEMINI_API_KEY from .env via python-dotenv if present.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"
STATE_PATH = ART / "state.json"
WAVE1 = [
    # Core standards already wired or high-value for CRE
    ("ASVS", "master", ["4.0/en/**/*.md", "5.0/en/**/*.md"]),
    ("CheatSheetSeries", "master", ["cheatsheets/**/*.md"]),
    ("wstg", "master", ["document/**/*.md"]),
    ("SAMM", "master", ["**/*.md"]),
    ("Top10", "master", ["**/*.md"]),
    ("API-Security", "master", ["**/*.md"]),
    ("mastg", "master", ["Document/**/*.md", "document/**/*.md", "**/*.md"]),
    ("masvs", "master", ["**/*.md"]),
    ("AISVS", "main", ["**/*.md"]),
    (
        "www-project-top-10-for-large-language-model-applications",
        "main",
        ["**/*.md"],
    ),
    ("www-project-proactive-controls", "main", ["**/*.md"]),
    ("www-project-ai-testing-guide", "main", ["**/*.md"]),
    ("www-project-ai-security-and-privacy-guide", "main", ["**/*.md"]),
    ("www-project-devsecops-guideline", "main", ["**/*.md"]),
    ("secure-coding-practices-quick-reference-guide", "master", ["**/*.md"]),
    ("DevSecOpsGuideline", "main", ["**/*.md"]),
    ("MCP-Security-Testing-Guide", "main", ["**/*.md"]),
    ("Software-Component-Verification-Standard", "main", ["**/*.md"]),
    ("IoT-Security-Verification-Standard-ISVS", "master", ["**/*.md"]),
    ("cornucopia", "master", ["**/*.md"]),
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("oie_owasp_eval")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def _load_state() -> Dict[str, Any]:
    return json.loads(STATE_PATH.read_text())


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = _now()
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
    (ART / "STATUS.md").write_text(
        f"# OIE OWASP eval status\n\n"
        f"- run_id: `{state['run_id']}`\n"
        f"- phase: **{state['phase']}**\n"
        f"- status: **{state['status']}**\n"
        f"- updated: {state['updated_at']}\n"
        f"- last_error: {state.get('last_error') or 'none'}\n"
        f"- human_gates: {json.dumps(state.get('human_gates') or [])}\n\n"
        f"## Phases\n\n"
        + "\n".join(
            f"- `{k}`: {v.get('status')}"
            + (f" — {v.get('detail', '')}" if v.get("detail") else "")
            for k, v in state["phases"].items()
        )
        + "\n"
    )


def _set_phase(
    state: Dict[str, Any],
    name: str,
    status: str,
    *,
    detail: str = "",
    make_current: bool = True,
) -> None:
    state["phases"][name] = {
        "status": status,
        "detail": detail,
        "at": _now(),
    }
    if make_current:
        state["phase"] = name
    _save_state(state)


def _repos_yaml_for(entries: List[tuple], path: Path) -> None:
    lines = ["repositories:\n"]
    for owner_repo, branch, includes in entries:
        rid = owner_repo.lower().replace("_", "-")
        lines.append(f"  - id: owasp-{rid}\n")
        lines.append("    type: github\n")
        lines.append("    enabled: true\n")
        lines.append("    owner: OWASP\n")
        lines.append(f"    repo: {owner_repo}\n")
        lines.append(f"    branch: {branch}\n")
        lines.append("    paths:\n")
        lines.append("      include:\n")
        for inc in includes:
            lines.append(f'        - "{inc}"\n')
        lines.append("      exclude:\n")
        lines.append('        - "**/archive/**"\n')
        lines.append('        - "**/.github/**"\n')
        lines.append('        - "**/node_modules/**"\n')
        lines.append("    chunking:\n")
        lines.append("      strategy: markdown_heading\n")
        lines.append("      max_tokens: 1200\n")
        lines.append("      overlap_tokens: 100\n")
        lines.append("    polling:\n")
        lines.append("      mode: incremental\n")
        lines.append("      interval_minutes: 1440\n")
        lines.append("\n")
    path.write_text("".join(lines))


def phase_bootstrap(state: Dict[str, Any]) -> None:
    _set_phase(state, "bootstrap", "running", detail="checking ollama + gemini key")
    _load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        state["human_gates"].append(
            {
                "id": "missing_gemini_key",
                "ask": "GEMINI_API_KEY missing from .env — add it to continue cloud classify/judge",
            }
        )
        state["status"] = "blocked"
        _set_phase(state, "bootstrap", "blocked", detail="GEMINI_API_KEY missing")
        return

    # Ensure ollama is up (best-effort).
    try:
        subprocess.run(
            ["ollama", "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        state["human_gates"].append(
            {
                "id": "ollama_down",
                "ask": f"Start `ollama serve` (need qwen2.5:14b). Error: {exc}",
            }
        )
        state["status"] = "blocked"
        _set_phase(state, "bootstrap", "blocked", detail=str(exc))
        return

    ART.mkdir(parents=True, exist_ok=True)
    _set_phase(state, "bootstrap", "ok", detail="keys + ollama ok")
    state["status"] = "running"
    state["phase"] = "generate_repos_yaml"
    _save_state(state)


def phase_generate_repos_yaml(state: Dict[str, Any]) -> None:
    _set_phase(state, "generate_repos_yaml", "running")
    wave1_path = ART / "repos_wave1.yaml"
    _repos_yaml_for(WAVE1, wave1_path)

    # Wave2: remaining candidates with broad **/*.md
    cands_path = ART / "candidates.json"
    wave2_entries: List[tuple] = []
    if cands_path.is_file():
        cands = json.loads(cands_path.read_text())
        wave1_names = {e[0] for e in WAVE1}
        for r in cands:
            name = r["name"]
            if name in wave1_names:
                continue
            # Prefer main; harvester will fail soft per-repo if wrong.
            wave2_entries.append((name, "main", ["**/*.md"]))
    wave2_path = ART / "repos_wave2.yaml"
    _repos_yaml_for(wave2_entries[:250], wave2_path)  # hard cap for laptop

    meta = {
        "wave1_repos": len(WAVE1),
        "wave2_repos": min(len(wave2_entries), 250),
        "wave1_yaml": str(wave1_path.relative_to(ROOT)),
        "wave2_yaml": str(wave2_path.relative_to(ROOT)),
    }
    (ART / "repos_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    _set_phase(
        state,
        "generate_repos_yaml",
        "ok",
        detail=f"wave1={meta['wave1_repos']} wave2={meta['wave2_repos']}",
    )
    state["phase"] = "harvest_wave1"
    _save_state(state)


def _run_harvester(run_id: str, repos_yaml: Path, db_url: str) -> Dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("FLASK_CONFIG", "development")
    env.setdefault("NO_LOAD_GRAPH_DB", "1")
    env["PYTHONPATH"] = str(ROOT)
    cmd = [
        sys.executable,
        str(ROOT / "cre.py"),
        "--run_harvester",
        "--run_id",
        run_id,
        "--cache_file",
        db_url,
        "--harvester_repos_yaml",
        str(repos_yaml),
    ]
    # Allow long clone/sync
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60 * 60 * 6,
    )
    out = (proc.stdout or "").strip().splitlines()
    summary: Dict[str, Any] = {"exit_code": proc.returncode, "raw_tail": out[-5:]}
    for line in reversed(out):
        line = line.strip()
        if line.startswith("{") and "run_id" in line:
            try:
                summary["summary"] = json.loads(line)
            except json.JSONDecodeError:
                pass
            break
    if proc.returncode != 0:
        summary["stderr_tail"] = (proc.stderr or "")[-2000:]
    return summary


def phase_harvest_wave1(state: Dict[str, Any]) -> None:
    """Prefer tarball harvest — agent sandboxes often forbid writing ``.git/``."""
    _set_phase(state, "harvest_wave1", "running", detail="tarball download + chunking")
    env = os.environ.copy()
    env.setdefault("FLASK_CONFIG", "development")
    env.setdefault("NO_LOAD_GRAPH_DB", "1")
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/oie_owasp_eval/tarball_harvest.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60 * 60 * 2,
    )
    (ART / "harvest_wave1.log").write_text(
        (proc.stdout or "") + "\n" + (proc.stderr or "")
    )
    # tarball_harvest updates state.json itself on success
    state = _load_state()
    if proc.returncode != 0 and state.get("phase") == "harvest_wave1":
        state["status"] = "error"
        state["last_error"] = (proc.stderr or proc.stdout or "")[-2000:]
        _set_phase(state, "harvest_wave1", "error", detail="tarball harvest failed")
        return
    # Ensure we advanced
    state = _load_state()
    if state.get("phase") == "classify_dual":
        return
    state["phase"] = "classify_dual"
    state["status"] = "running"
    _save_state(state)


def _snapshot_harvest(db_url: str, run_id: str) -> Dict[str, Any]:
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    sys.path.insert(0, str(ROOT))
    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.database.db import HarvestInput

    db_connect(db_url)
    rows = sqla.session.query(HarvestInput).filter_by(pipeline_run_id=run_id).all()
    by_repo: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.payload or {}
        repo = payload.get("source_repo") or "unknown"
        by_repo[repo] = by_repo.get(repo, 0) + 1
        if len(samples) < 25:
            samples.append(
                {
                    "chunk_id": payload.get("chunk_id"),
                    "source_repo": repo,
                    "locator_path": payload.get("locator_path")
                    or (payload.get("locator") or {}).get("path"),
                    "text_preview": (payload.get("text") or "")[:180],
                    "status": row.status,
                }
            )
    return {
        "run_id": run_id,
        "total_rows": len(rows),
        "by_repo": dict(sorted(by_repo.items(), key=lambda kv: -kv[1])),
        "samples": samples,
    }


def _reset_harvest_pending(db_url: str, run_id: str) -> None:
    sys.path.insert(0, str(ROOT))
    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.database.db import HarvestInput

    db_connect(db_url)
    (
        sqla.session.query(HarvestInput)
        .filter_by(pipeline_run_id=run_id)
        .update({"status": "pending"}, synchronize_session=False)
    )
    sqla.session.commit()


def _run_noise_filter(db_url: str, run_id: str, model: str) -> Dict[str, Any]:
    env = os.environ.copy()
    # Ensure .env keys are present for LiteLLM (cre.py child).
    _load_dotenv()
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CRE_NOISE_FILTER_LLM_MODEL"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.setdefault("FLASK_CONFIG", "development")
    env.setdefault("NO_LOAD_GRAPH_DB", "1")
    env["PYTHONPATH"] = str(ROOT)
    env["CRE_NOISE_FILTER_LLM_MODEL"] = model
    # Smaller batches for local model / flaky pro
    if model.startswith("ollama/"):
        env["CRE_NOISE_FILTER_BATCH_SIZE"] = "4"
        env["CRE_NOISE_FILTER_MAX_CHARS"] = "1200"
    elif "pro" in model:
        env["CRE_NOISE_FILTER_BATCH_SIZE"] = "5"
        env["CRE_LLM_MAX_RETRIES"] = "4"
        env["CRE_LLM_RETRY_SLEEP_SECONDS"] = "20"
    else:
        env["CRE_NOISE_FILTER_BATCH_SIZE"] = "10"
    cmd = [
        sys.executable,
        str(ROOT / "cre.py"),
        "--run_noise_filter",
        "--run_id",
        run_id,
        "--cache_file",
        db_url,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60 * 60 * 8,
    )
    out = (proc.stdout or "").strip().splitlines()
    summary: Dict[str, Any] = {"exit_code": proc.returncode, "model": model}
    for line in reversed(out):
        if line.strip().startswith("{") and "run_id" in line:
            try:
                summary["summary"] = json.loads(line.strip())
            except json.JSONDecodeError:
                pass
            break
    if proc.returncode != 0:
        summary["stderr_tail"] = (proc.stderr or "")[-2000:]
    return summary


def _snapshot_knowledge(db_url: str, run_id: str) -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.database.db import KnowledgeQueueItem

    db_connect(db_url)
    rows = (
        sqla.session.query(KnowledgeQueueItem).filter_by(pipeline_run_id=run_id).all()
    )
    by_label: Dict[str, int] = {}
    by_repo: Dict[str, int] = {}
    keepers: List[Dict[str, Any]] = []
    for row in rows:
        by_label[row.llm_label] = by_label.get(row.llm_label, 0) + 1
        by_repo[row.source_repo] = by_repo.get(row.source_repo, 0) + 1
        keepers.append(
            {
                "chunk_id": row.chunk_id,
                "source_repo": row.source_repo,
                "locator_path": row.locator_path,
                "llm_label": row.llm_label,
                "confidence": row.confidence,
                "text_preview": (row.text or "")[:200],
            }
        )
    return {
        "run_id": run_id,
        "total": len(rows),
        "by_label": by_label,
        "by_repo": dict(sorted(by_repo.items(), key=lambda kv: -kv[1])),
        "would_flow_to_c": keepers,
    }


def _sample_harvest_for_eval(
    db_url: str, run_id: str, *, per_repo: int = 25, max_total: int = 400
) -> str:
    """Copy a stratified sample of harvest rows to a new run_id for dual classify."""
    import copy
    from collections import defaultdict

    sys.path.insert(0, str(ROOT))
    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import HarvestInput

    db_connect(db_url)
    rows = sqla.session.query(HarvestInput).filter_by(pipeline_run_id=run_id).all()
    by_repo: Dict[str, list] = defaultdict(list)
    for row in rows:
        repo = (
            (row.payload or {}).get("source_repo")
            or ((row.payload or {}).get("source") or {}).get("repo")
            or "unknown"
        )
        by_repo[repo].append(row)

    sample_run = run_id + "-sample"
    # wipe prior sample
    (
        sqla.session.query(HarvestInput)
        .filter_by(pipeline_run_id=sample_run)
        .delete(synchronize_session=False)
    )
    picked = 0
    for repo, repo_rows in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        if picked >= max_total:
            break
        take = min(per_repo, max_total - picked, len(repo_rows))
        # spread: first, middle, last-ish
        idxs = sorted(
            {
                0,
                len(repo_rows) // 2,
                len(repo_rows) - 1,
                *[i * max(len(repo_rows) // take, 1) for i in range(take)],
            }
        )[:take]
        for i in idxs:
            row = repo_rows[i]
            payload = copy.deepcopy(row.payload or {})
            payload["pipeline_run_id"] = sample_run
            sqla.session.add(
                HarvestInput(
                    pipeline_run_id=sample_run, status="pending", payload=payload
                )
            )
            picked += 1
    sqla.session.commit()
    meta = {
        "source_run": run_id,
        "sample_run": sample_run,
        "source_total": len(rows),
        "sample_total": picked,
        "per_repo": per_repo,
        "by_repo_source": {k: len(v) for k, v in by_repo.items()},
    }
    (ART / "classify_sample_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return sample_run


def phase_classify_dual(state: Dict[str, Any]) -> None:
    _load_dotenv()
    _set_phase(state, "classify_dual", "running", detail="sample → qwen → gemini")
    db_url = state["db_url"]
    base_run = state["wave1_run_id"]
    local_model = state["models"]["local"]
    cloud_model = state["models"]["cloud"]

    sample_run = _sample_harvest_for_eval(db_url, base_run)
    state["sample_run_id"] = sample_run
    _save_state(state)

    local = _run_noise_filter(db_url, sample_run, local_model)
    local_snap = _snapshot_knowledge(db_url, sample_run)
    (ART / "classify_qwen.json").write_text(
        json.dumps({"result": local, "knowledge": local_snap}, indent=2) + "\n"
    )

    gem_run = sample_run + "-gemini"
    _clone_harvest_run(db_url, sample_run, gem_run)
    # Reset sample rows already marked processed so clone is the only gemini input
    gem = _run_noise_filter(db_url, gem_run, cloud_model)
    gem_snap = _snapshot_knowledge(db_url, gem_run)
    (ART / "classify_gemini.json").write_text(
        json.dumps({"result": gem, "knowledge": gem_snap}, indent=2) + "\n"
    )

    qwen_ids = {k["chunk_id"] for k in local_snap["would_flow_to_c"]}
    gem_ids = {k["chunk_id"] for k in gem_snap["would_flow_to_c"]}
    diff = {
        "qwen_only": sorted(qwen_ids - gem_ids),
        "gemini_only": sorted(gem_ids - qwen_ids),
        "both": sorted(qwen_ids & gem_ids),
        "qwen_count": len(qwen_ids),
        "gemini_count": len(gem_ids),
        "agreement_rate": (
            round(len(qwen_ids & gem_ids) / max(len(qwen_ids | gem_ids), 1), 4)
        ),
        "note": "Dual classify runs on stratified sample; see classify_sample_meta.json",
    }
    (ART / "classify_diff.json").write_text(json.dumps(diff, indent=2) + "\n")

    state["gemini_run_id"] = gem_run
    _set_phase(
        state,
        "classify_dual",
        "ok",
        detail=(
            f"qwen={diff['qwen_count']} gemini={diff['gemini_count']} "
            f"agree={diff['agreement_rate']}"
        ),
    )
    state["phase"] = "judge"
    _save_state(state)


def _clone_harvest_run(db_url: str, src_run: str, dst_run: str) -> None:
    sys.path.insert(0, str(ROOT))
    from application.cmd.cre_main import db_connect
    from application import sqla
    from application.database.db import HarvestInput
    import copy

    db_connect(db_url)
    rows = sqla.session.query(HarvestInput).filter_by(pipeline_run_id=src_run).all()
    for row in rows:
        payload = copy.deepcopy(row.payload or {})
        payload["pipeline_run_id"] = dst_run
        sqla.session.add(
            HarvestInput(
                pipeline_run_id=dst_run,
                status="pending",
                payload=payload,
            )
        )
    sqla.session.commit()


def phase_judge(state: Dict[str, Any]) -> None:
    """Ask Gemini-pro to flag nonsensical keepers / improvement areas."""
    _load_dotenv()
    _set_phase(state, "judge", "running")
    gem = json.loads((ART / "classify_gemini.json").read_text())
    qwen = json.loads((ART / "classify_qwen.json").read_text())
    diff = json.loads((ART / "classify_diff.json").read_text())
    harvest = json.loads((ART / "harvest_wave1_snapshot.json").read_text())

    keepers = gem["knowledge"]["would_flow_to_c"][:80]
    disagreements = []
    qwen_map = {k["chunk_id"]: k for k in qwen["knowledge"]["would_flow_to_c"]}
    gem_map = {k["chunk_id"]: k for k in gem["knowledge"]["would_flow_to_c"]}
    for cid in (diff["qwen_only"] + diff["gemini_only"])[:40]:
        disagreements.append(
            {
                "chunk_id": cid,
                "in_qwen": cid in qwen_map,
                "in_gemini": cid in gem_map,
                "sample": qwen_map.get(cid) or gem_map.get(cid),
            }
        )

    prompt = {
        "task": (
            "You are reviewing OpenCRE Module B noise-filter output for an OWASP "
            "harvest. Flag keepers that should NOT become CRE knowledge (noise, "
            "meta, marketing, chapter logistics without security content, empty "
            "stubs, license-only, contributor lists). Suggest concrete pipeline "
            "improvements for Module A path filters and Module B prompts."
        ),
        "harvest_totals": harvest.get("by_repo"),
        "agreement": {
            "qwen_count": diff["qwen_count"],
            "gemini_count": diff["gemini_count"],
            "agreement_rate": diff["agreement_rate"],
        },
        "sample_keepers_gemini": keepers,
        "disagreements": disagreements,
    }

    import litellm  # type: ignore

    resp = litellm.completion(
        model=state["models"]["judge"],
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "Respond with JSON only: {"
                    '"nonsensical_keepers":[{"chunk_id":"","reason":""}],'
                    '"false_drops_suspected":[{"chunk_id":"","reason":""}],'
                    '"path_filter_improvements":[""],'
                    '"prompt_improvements":[""],'
                    '"orchestrator_improvements":[""],'
                    '"summary":""}'
                ),
            },
            {"role": "user", "content": json.dumps(prompt)[:120000]},
        ],
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        verdict = {"raw": text, "summary": "judge returned non-JSON"}

    (ART / "judge_report.json").write_text(json.dumps(verdict, indent=2) + "\n")
    _set_phase(state, "judge", "ok", detail=(verdict.get("summary") or "")[:200])
    state["phase"] = "next_steps_doc"
    # Skip wave2 auto for now unless human wants — mark pending optional
    state["phases"]["harvest_wave2"] = {
        "status": "deferred",
        "detail": "Wave2 (250 repos) deferred until you approve overnight cost/time",
        "at": _now(),
    }
    state["human_gates"].append(
        {
            "id": "approve_wave2",
            "ask": (
                "Wave1 judge done. Approve Wave2 harvest of ~250 more OWASP "
                "www-project repos? Reply: approve wave2 | skip wave2"
            ),
        }
    )
    _save_state(state)


def phase_next_steps_doc(state: Dict[str, Any]) -> None:
    _set_phase(state, "next_steps_doc", "running")
    judge = {}
    if (ART / "judge_report.json").is_file():
        judge = json.loads((ART / "judge_report.json").read_text())
    diff = {}
    if (ART / "classify_diff.json").is_file():
        diff = json.loads((ART / "classify_diff.json").read_text())
    harvest = {}
    if (ART / "harvest_wave1_snapshot.json").is_file():
        harvest = json.loads((ART / "harvest_wave1_snapshot.json").read_text())

    doc = f"""# Next steps — OIE → MCP / agent for human Q&A

**Audience:** OpenCRE maintainers. **Status:** draft from eval run `{state['run_id']}` ({_now()}).

## What we just proved

- Module A can harvest configured OWASP markdown into `harvest_input`.
- Module B (local Qwen 14B vs Gemini 2.5 Pro) can label keepers that would enter `knowledge_queue` (Module C input).
- Wave1 harvest rows: **{harvest.get('total_rows', 'n/a')}**; Qwen keepers: **{diff.get('qwen_count', 'n/a')}**; Gemini keepers: **{diff.get('gemini_count', 'n/a')}**; agreement: **{diff.get('agreement_rate', 'n/a')}**.
- Judge summary: {judge.get('summary', '(pending)')}

## Product shape: “ask OpenCRE anything”

Humans will ask two different classes of questions:

| Class | Example | Backing |
|-------|---------|---------|
| **Normative / CRE** | “How should I store passwords?” | CRE graph + Module C/D links + standards chunks |
| **Procedural / community** | “I’m in place X — when is the nearest OWASP meeting?” | Chapter calendars, Meetup/ICS feeds, chapter repos — **not** CRE nodes |

Do **not** force procedural answers through the Librarian→CRE path. Add a **router** in the agent/MCP layer.

## Proposed MCP server: `opencre`

Tools (v1):

1. `cre_search` — semantic + keyword over CRE / standards (existing chat/embeddings).
2. `standard_lookup` — ASVS/WSTG/CheatSheet section by id/path.
3. `pipeline_status` — last OIE run_id, queue depths, degraded flags.
4. `harvest_diff` — “what would Module C see for run R?”
5. `chapter_events_near` — geocode + nearest upcoming OWASP chapter events (new).
6. `ask` — natural-language entry that **routes** to 1–5.

Resources:

- `opencre://cre/{{id}}`
- `opencre://run/{{pipeline_run_id}}/knowledge`
- `opencre://chapters/events?lat=&lon=`

## Architecture

```
Human / IDE agent
    │  MCP (stdio or HTTP)
    ▼
opencre-mcp router
    ├─ intent: security knowledge → PromptHandler / CRE + optional OIE citations
    ├─ intent: pipeline ops → read harvest_input / knowledge_queue / decision_queue
    └─ intent: community logistics → chapter calendar provider (Meetup GraphQL,
         chapter site ICS, or curated OWASP chapter JSON — start curated)
```

Nightly Cursor Automation / cron:

1. `make oie-pipeline` (A→B→C) for configured `repos.yaml`
2. Publish run summary JSON to `tmp/` or S3; MCP `pipeline_status` reads it
3. Optional: Slack digest of “new KNOWLEDGE chunks this week”

## Implementation sequence

1. **Ship Wave1 repos.yaml** curated list into `application/utils/harvester/repos.yaml` after path-filter nits from judge.
2. **MCP skeleton** under `scripts/mcp_opencre/` (repo already notes MCP in requirements-dev) — tools 1, 3, 4 first.
3. **Router prompt** with hard rule: logistics ≠ CRE.
4. **Chapter events v0:** curated JSON of major chapters + Meetup links; `chapter_events_near` uses Haversine; no scrape war.
5. **Eval harness** (this run) as `make oie-owasp-eval` for dual-model CI smoke on a tiny fixture.

## Judge-driven improvements to fold in

{json.dumps(judge.get('path_filter_improvements') or [], indent=2)}

{json.dumps(judge.get('prompt_improvements') or [], indent=2)}

{json.dumps(judge.get('orchestrator_improvements') or [], indent=2)}

## Human gates remaining

{json.dumps(state.get('human_gates') or [], indent=2)}

## Out of scope for MCP v1

- Writing CRE links from chat (Module D human review stays)
- Running paid Gemini classify on every IDE keystroke
- Scraping every OWASP chapter website without ToS review
"""

    out = ROOT / "docs" / "gsoc_2026_module_a" / "next_steps_mcp_agent.md"
    out.write_text(doc)
    (ART / "next_steps_mcp_agent.md").write_text(doc)
    _set_phase(state, "next_steps_doc", "ok", detail=str(out.relative_to(ROOT)))
    state["phase"] = "done"
    state["phases"]["done"] = {
        "status": "ok",
        "detail": "observe artifacts under tmp/oie_owasp_eval; approve wave2 if desired",
        "at": _now(),
    }
    state["status"] = "awaiting_human" if state.get("human_gates") else "done"
    _save_state(state)


PHASES = {
    "bootstrap": phase_bootstrap,
    "generate_repos_yaml": phase_generate_repos_yaml,
    "harvest_wave1": phase_harvest_wave1,
    "classify_dual": phase_classify_dual,
    "judge": phase_judge,
    "next_steps_doc": phase_next_steps_doc,
}


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.is_file():
        print("missing state.json", file=sys.stderr)
        return 2
    state = _load_state()
    if state.get("status") == "blocked":
        print(json.dumps({"blocked": True, "gates": state.get("human_gates")}))
        return 3
    phase = state.get("phase") or "bootstrap"
    if phase == "done":
        print(json.dumps({"done": True, "state": state}))
        return 0
    if phase == "harvest_wave2":
        print(
            json.dumps({"waiting": "approve_wave2", "gates": state.get("human_gates")})
        )
        return 0
    fn = PHASES.get(phase)
    if not fn:
        print(f"unknown phase {phase}", file=sys.stderr)
        return 2
    try:
        fn(state)
    except Exception as exc:  # noqa: BLE001
        state = _load_state()
        state["status"] = "error"
        state["last_error"] = f"{exc}\n{traceback.format_exc()[-1500:]}"
        _set_phase(state, phase, "error", detail=str(exc))
        print(state["last_error"], file=sys.stderr)
        return 1
    state = _load_state()
    print(json.dumps({"phase": state["phase"], "status": state["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
