#!/usr/bin/env python3
"""Exhaustive B2 switch grid on shared harvest + Module C re-score.

Canonical gold only (``local_gold: false``); Agentic excluded from headline.
Reuses ``orch-exp-baseline-20260921`` knowledge_queue; clears decisions and
re-runs Module C per combo.

Writes:
  tmp/oie_owasp_eval/experiments/grid/<id>.json
  tmp/oie_owasp_eval/experiments/grid/master.csv
  tmp/oie_owasp_eval/experiments/grid/comparison.md
  tmp/oie_owasp_eval/experiments/comparison.md  (grid summary pointer + top)

Fixed (not axes): PRIOR_CAGE / PREF_INJECT / PREFER_AUDIT_IDS = Lawrence on;
STANDARD_RETRIEVAL off; SHORTLIST_JUDGE off (deterministic, no Gemini judge);
CRE_LIBRARIAN_DEVICE=cpu; trained CE not in grid.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP_ART = ROOT / "tmp" / "oie_owasp_eval" / "experiments"
GRID_DIR = EXP_ART / "grid"
LOCKS_DIR = GRID_DIR / ".locks"
COMPARISON_MD = EXP_ART / "comparison.md"
GRID_COMPARISON_MD = GRID_DIR / "comparison.md"
MASTER_CSV = GRID_DIR / "master.csv"
STATE_PATH = GRID_DIR / "_state.json"
ARTIFACTS_LOCKDIR = GRID_DIR / ".artifacts_rebuild.lockdir"
WINNERS_MD = ROOT / "scripts" / "oie_owasp_eval" / "experiments" / "WINNERS.md"
STACK_YAML = ROOT / "scripts" / "oie_owasp_eval" / "experiments" / "stack_winners.yaml"
EMBED_CACHE_DIR = ROOT / "tmp" / "oie_owasp_eval" / "embed_cache"

RUN_ID = "orch-exp-baseline-20260921"
DEFAULT_DB_URL = "postgresql://cre:password@127.0.0.1:5432/cre"
_EMBED_CACHE_INSTALLED = False
_EMBED_CACHE_STATS = {"hit": 0, "miss": 0}
_DB_HANDLE: Any = None
_CE_WARMED = False

# Axes inventory (eval-time boolean / discrete toggles).
# Order is stable and encoded into combo ids.
AXES: List[Dict[str, Any]] = [
    {
        "key": "cre_summary",
        "env": "CRE_LIBRARIAN_CRE_SUMMARY",
        "levels": (("0", False), ("1", True)),
        "note": "CRE search blurbs",
    },
    {
        "key": "dual_index",
        "env": "CRE_LIBRARIAN_DUAL_INDEX",
        "levels": (("0", False), ("1", True)),
        "note": "title vs body pools; typically needs cre_summary",
    },
    {
        "key": "use_rrf",
        "env": "CRE_LIBRARIAN_USE_RRF",
        "levels": (("0", False), ("1", True)),
        "note": "RRF merge; NO-OP unless dual_index=1",
    },
    {
        "key": "context_enrich",
        "env": "CRE_LIBRARIAN_CONTEXT_ENRICH",
        "levels": (("0", False), ("1", True)),
        "note": "prefix Standard/Section when missing",
    },
    {
        "key": "margin_gamma",
        "env": "CRE_LIBRARIAN_MARGIN_GAMMA",
        "levels": (("off", None), ("0.85", "0.85")),
        "note": "relative margin cutoff; off vs 0.85",
    },
    {
        "key": "hub_leaf_cage",
        "env": "CRE_LIBRARIAN_HUB_LEAF_CAGE",
        "levels": (("0", False), ("1", True)),
        "note": "hub→leaf cage",
    },
    {
        "key": "focus_query",
        "env": "CRE_LIBRARIAN_FOCUS_QUERY",
        "levels": (("0", False), ("1", True)),
        "note": "Lawrence FOCUS_QUERY on/off (default off)",
    },
    {
        "key": "hybrid",
        "env": None,  # multi-env
        "levels": (
            ("lawrence", {"CRE_LIBRARIAN_HYBRID_BETA": "0", "CRE_LIBRARIAN_HYBRID_GAMMA": "0.70"}),
            (
                "nameheavy",
                {
                    "CRE_LIBRARIAN_HYBRID_BETA": "3.0",
                    "CRE_LIBRARIAN_HYBRID_GAMMA": "0.15",
                },
            ),
        ),
        "note": "CE-led β=0/γ=0.70 vs name-heavy β=3.0/γ=0.15",
    },
    {
        "key": "cre_text_enrich",
        "env": "CRE_LIBRARIAN_CRE_TEXT_ENRICH",
        "levels": (("0", False), ("1", True)),
        "note": "CRE text enrich (already-wired boolean)",
    },
]

FIXED_ENV: Dict[str, str] = {
    "CRE_LIBRARIAN_PRIOR_CAGE": "1",
    "CRE_LIBRARIAN_PREF_INJECT": "1",
    "CRE_LIBRARIAN_PREFER_AUDIT_IDS": "1",
    # Fixed OFF for the 512-combo grid: Gemini shortlist-judge hangs (0% CPU
    # multi-minute stalls) made judge-ON factorial infeasible. Absolute scores
    # are lower than Phase-3 one-factor (judge ON); relative ranking is under
    # a consistent judge-off regime. Not a grid axis.
    "CRE_LIBRARIAN_SHORTLIST_JUDGE": "0",
    "CRE_LIBRARIAN_DEVICE": "cpu",
    "CRE_LIBRARIAN_RETRIEVER_BACKEND": "pgvector",
}

CLEAR_ENV: Tuple[str, ...] = (
    "CRE_LIBRARIAN_CRE_SUMMARY",
    "CRE_LIBRARIAN_DUAL_INDEX",
    "CRE_LIBRARIAN_USE_RRF",
    "CRE_LIBRARIAN_CONTEXT_ENRICH",
    "CRE_LIBRARIAN_MARGIN_GAMMA",
    "CRE_LIBRARIAN_HUB_LEAF_CAGE",
    "CRE_LIBRARIAN_FOCUS_QUERY",
    "CRE_LIBRARIAN_HYBRID_BETA",
    "CRE_LIBRARIAN_HYBRID_GAMMA",
    "CRE_LIBRARIAN_CRE_TEXT_ENRICH",
    "CRE_LIBRARIAN_STANDARD_RETRIEVAL",
    "CRE_LIBRARIAN_CROSSENCODER_MODEL",
)

AGENTIC_LABEL = "OWASP Agentic AI (stub, no hub Links)"


def total_combos() -> int:
    n = 1
    for ax in AXES:
        n *= len(ax["levels"])
    return n


def _level_tag(ax: Mapping[str, Any], level: Tuple[Any, Any]) -> str:
    return str(level[0])


def iter_combos() -> Iterable[Tuple[str, Dict[str, str], Dict[str, Any], List[str]]]:
    """Yield (combo_id, env_flags, axis_vector, notes)."""
    level_lists = [list(ax["levels"]) for ax in AXES]
    for picks in itertools.product(*level_lists):
        tags = [_level_tag(AXES[i], picks[i]) for i in range(len(AXES))]
        # Compact id: g_<tags joined by _>
        combo_id = "g_" + "_".join(tags)
        env: Dict[str, str] = {}
        vector: Dict[str, Any] = {}
        notes: List[str] = []
        for ax, pick in zip(AXES, picks):
            tag, val = pick
            vector[ax["key"]] = tag
            if ax["key"] == "hybrid":
                assert isinstance(val, dict)
                env.update({k: str(v) for k, v in val.items()})
            elif ax["key"] == "margin_gamma":
                if val is None:
                    # leave unset (= off)
                    pass
                else:
                    env["CRE_LIBRARIAN_MARGIN_GAMMA"] = str(val)
            else:
                env[ax["env"]] = "1" if val else "0"
        # No-op annotations
        if vector.get("use_rrf") == "1" and vector.get("dual_index") == "0":
            notes.append("noop: USE_RRF without DUAL_INDEX")
        if vector.get("dual_index") == "1" and vector.get("cre_summary") == "0":
            notes.append("dual_index without cre_summary (may be weak / empty summary pool)")
        yield combo_id, env, vector, notes


def parse_db_url(url: Optional[str] = None) -> Dict[str, str]:
    """Parse DEV_DATABASE_URL into psql connection pieces."""
    raw = url or os.environ.get("DEV_DATABASE_URL") or DEFAULT_DB_URL
    parsed = urlparse(raw)
    db = (parsed.path or "/cre").lstrip("/") or "cre"
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "cre",
        "password": parsed.password or os.environ.get("PGPASSWORD", "password"),
        "dbname": db,
        "url": raw,
    }


def reset_queues() -> None:
    """Clear decisions + unconsume KQ for RUN_ID on *this worker's* database."""
    conn = parse_db_url()
    sql = (
        f"DELETE FROM decision_queue WHERE pipeline_run_id = '{RUN_ID}'; "
        f"UPDATE knowledge_queue SET consumed_at = NULL "
        f"WHERE pipeline_run_id = '{RUN_ID}';"
    )
    subprocess.run(
        [
            "psql",
            "-h",
            conn["host"],
            "-p",
            conn["port"],
            "-U",
            conn["user"],
            "-d",
            conn["dbname"],
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        check=True,
        env={**os.environ, "PGPASSWORD": conn["password"]},
    )


def claim_combo(combo_id: str) -> bool:
    """Exclusive claim via mkdir lockdir so parallel workers never double-write.

    Returns False if another worker holds the claim or a completed JSON exists.
    """
    out = GRID_DIR / f"{combo_id}.json"
    if out.is_file():
        try:
            data = json.loads(out.read_text())
            if data.get("status") == "ok" and data.get("headline"):
                return False
        except (json.JSONDecodeError, OSError):
            pass
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock = LOCKS_DIR / combo_id
    try:
        lock.mkdir()
        (lock / "pid").write_text(f"{os.getpid()}\n")
        return True
    except FileExistsError:
        return False


def release_combo_claim(combo_id: str) -> None:
    """Drop claim after a failed combo so another worker/resume can retry."""
    lock = LOCKS_DIR / combo_id
    if not lock.is_dir():
        return
    try:
        for child in lock.iterdir():
            child.unlink(missing_ok=True)
        lock.rmdir()
    except OSError:
        pass


def write_combo_json_atomic(combo_id: str, payload: Mapping[str, Any]) -> Path:
    """Write g_<id>.json via temp + rename (no partial JSON visible)."""
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    out = GRID_DIR / f"{combo_id}.json"
    tmp = GRID_DIR / f".{combo_id}.{os.getpid()}.tmp.json"
    text = json.dumps(dict(payload), indent=2, default=str) + "\n"
    tmp.write_text(text)
    os.replace(tmp, out)
    return out


def try_acquire_artifacts_lock(timeout_sec: float = 30.0) -> bool:
    """mkdir flock for master.csv / comparison / winners rebuild."""
    deadline = time.time() + timeout_sec
    ARTIFACTS_LOCKDIR.parent.mkdir(parents=True, exist_ok=True)
    while time.time() < deadline:
        try:
            ARTIFACTS_LOCKDIR.mkdir()
            (ARTIFACTS_LOCKDIR / "pid").write_text(f"{os.getpid()}\n")
            return True
        except FileExistsError:
            # Stale lock reclaim if holder is dead.
            try:
                pid_s = (ARTIFACTS_LOCKDIR / "pid").read_text().strip()
                pid = int(pid_s) if pid_s else 0
            except (OSError, ValueError):
                pid = 0
            if pid and pid != os.getpid():
                try:
                    os.kill(pid, 0)
                except OSError:
                    try:
                        for child in ARTIFACTS_LOCKDIR.iterdir():
                            child.unlink(missing_ok=True)
                        ARTIFACTS_LOCKDIR.rmdir()
                        continue
                    except OSError:
                        pass
            time.sleep(0.25)
    return False


def release_artifacts_lock() -> None:
    if not ARTIFACTS_LOCKDIR.is_dir():
        return
    try:
        for child in ARTIFACTS_LOCKDIR.iterdir():
            child.unlink(missing_ok=True)
        ARTIFACTS_LOCKDIR.rmdir()
    except OSError:
        pass


def clear_and_apply(flags: Mapping[str, str]) -> None:
    for k in CLEAR_ENV:
        os.environ.pop(k, None)
    for k, v in FIXED_ENV.items():
        os.environ[k] = v
    for k, v in flags.items():
        os.environ[k] = str(v)


def install_query_embed_disk_cache() -> None:
    """Cache PromptHandler.get_text_embeddings by sha256(text) across combos.

    Many grid axes (hybrid / margin / hub_leaf / dual / summary / rrf) do not
    change the query string, so Module C re-embeds identical text hundreds of
    times. Disk cache keeps Gemini calls off the hot path after the first miss.
    Safe for this eval harness only (monkeypatch).
    """
    global _EMBED_CACHE_INSTALLED
    if _EMBED_CACHE_INSTALLED:
        return
    from application.prompt_client.prompt_client import PromptHandler

    EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    original = PromptHandler.get_text_embeddings

    def _cached(self: Any, text: Any) -> Any:
        if not isinstance(text, str):
            return original(self, text)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        path = EMBED_CACHE_DIR / f"{key}.json"
        if path.is_file():
            try:
                _EMBED_CACHE_STATS["hit"] += 1
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        _EMBED_CACHE_STATS["miss"] += 1
        vec = original(self, text)
        try:
            path.write_text(json.dumps(list(vec)))
        except OSError:
            pass
        return vec

    PromptHandler.get_text_embeddings = _cached  # type: ignore[method-assign]
    _EMBED_CACHE_INSTALLED = True
    print(f"EMBED_CACHE dir={EMBED_CACHE_DIR}", flush=True)


def get_database() -> Any:
    """Reuse one DB handle across combos (same process, shared harvest)."""
    global _DB_HANDLE
    if _DB_HANDLE is None:
        from application.cmd.cre_main import db_connect

        _DB_HANDLE = db_connect(path=os.environ["DEV_DATABASE_URL"])
    return _DB_HANDLE


def warm_cross_encoder() -> None:
    """Load CE once before the first Module C combo (kept warm via process cache)."""
    global _CE_WARMED
    if _CE_WARMED:
        return
    from application.utils.librarian.cross_encoder import (
        DEFAULT_CROSSENCODER_MODEL,
        build_cross_encoder_score_fn,
    )

    model = os.environ.get("CRE_LIBRARIAN_CROSSENCODER_MODEL") or DEFAULT_CROSSENCODER_MODEL
    build_cross_encoder_score_fn(model)
    _CE_WARMED = True
    print(f"CE_WARM model={model} device={os.environ.get('CRE_LIBRARIAN_DEVICE', '')}", flush=True)


def run_module_c(flags: Mapping[str, str]) -> Dict[str, Any]:
    clear_and_apply(flags)
    install_query_embed_disk_cache()
    warm_cross_encoder()
    from application.utils.librarian.config_loader import load_config
    from application.utils.librarian.envelope_sink import DbEnvelopeSink
    from application.utils.librarian.factory import build_components
    from application.utils.librarian.queue_runner import run_librarian_queue

    cfg = load_config()
    snapshot = {
        k: getattr(cfg, k)
        for k in (
            "cre_summary",
            "dual_index",
            "use_rrf",
            "context_enrich",
            "margin_gamma",
            "hub_leaf_cage",
            "focus_query",
            "hybrid_beta",
            "hybrid_gamma",
            "cre_text_enrich",
            "prior_cage",
            "pref_inject",
            "prefer_audit_ids",
        )
    }
    database = get_database()
    components = build_components(database, config=cfg)
    sink = DbEnvelopeSink(database.session, RUN_ID)
    summary = run_librarian_queue(
        database.session,
        RUN_ID,
        components,
        cfg,
        at=datetime.now(timezone.utc),
        sink=sink,
        dry_run=False,
    )
    payload = (
        summary
        if isinstance(summary, dict)
        else getattr(summary, "__dict__", {"raw": str(summary)})
    )
    return {"config": snapshot, "summary": payload}


def score_b2(out_path: Path) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"),
        "--score-only",
        "--run-id",
        RUN_ID,
        "--out",
        str(out_path),
        "--exclude-fixtures",
        "owasp_asvs_5_0_provisional",
    ]
    # Default excludes agentic unless --include-agentic.
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    if proc.returncode != 0 or not out_path.is_file():
        return {"status": "failed", "returncode": proc.returncode}
    report = json.loads(out_path.read_text())
    return {"status": "ok", "returncode": 0, "report": report}


def headline_from_b2(report: Mapping[str, Any]) -> Dict[str, Any]:
    by_resource = dict(report.get("by_resource") or {})
    hits = scorable = 0
    families: Dict[str, Any] = {}
    for label, bucket in by_resource.items():
        if label == AGENTIC_LABEL:
            continue
        families[label] = bucket
        hits += int(bucket.get("hits") or 0)
        scorable += int(bucket.get("scorable") or 0)
    accuracy = round((hits / scorable) if scorable else 0.0, 4)
    agentic = by_resource.get(AGENTIC_LABEL)
    return {
        "hits": hits,
        "scorable": scorable,
        "accuracy": accuracy,
        "by_resource": families,
        "excluded_resources": [AGENTIC_LABEL],
        "agentic_stub": dict(agentic) if agentic is not None else None,
        "footnote": (
            "Agentic AI stub has no hub Links; exclude from headline denominator."
        ),
    }


def write_axes_preamble(path: Path, *, completed: int = 0) -> None:
    n = total_combos()
    lines = [
        "# Exhaustive B2 switch grid",
        "",
        f"**Shared harvest:** `{RUN_ID}` (Module C re-score per combo)",
        "**Gold:** canonical (`local_gold: false`); Agentic excluded from headline",
        f"**Device:** `CRE_LIBRARIAN_DEVICE=cpu`; `CRE_LIBRARIAN_SHORTLIST_JUDGE=0` "
        f"(fixed; Gemini judge hangs blocked judge-ON factorial)",
        f"**Combos:** {n} full factorial ({completed} completed)",
        "",
        "## Axes",
        "",
        "| axis | env / levels | note |",
        "|---|---|---|",
    ]
    for ax in AXES:
        levels = ", ".join(str(t[0]) for t in ax["levels"])
        env = ax["env"] or "CRE_LIBRARIAN_HYBRID_BETA + HYBRID_GAMMA"
        lines.append(f"| `{ax['key']}` | `{env}` → {levels} | {ax['note']} |")
    lines.extend(
        [
            "",
            "## Fixed (not grid axes)",
            "",
            "- `PRIOR_CAGE=1`, `PREF_INJECT=1`, `PREFER_AUDIT_IDS=1` (Lawrence defaults)",
            "- `STANDARD_RETRIEVAL` off",
            "- Trained cross-encoder deferred (not in this grid)",
            "- ASVS5 harvest excluded (chapter HTML OOM risk)",
            "",
            f"Total = {' × '.join(str(len(a['levels'])) for a in AXES)} = **{n}**",
            "",
            "## Ranked results (hits/scorable)",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def load_completed() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not GRID_DIR.is_dir():
        return out
    for path in GRID_DIR.glob("g_*.json"):
        # Skip scoring side-cars: g_<id>.b2_report.json
        if path.name.endswith(".b2_report.json") or ".b2_report." in path.name:
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if data.get("headline") and data.get("status") == "ok":
            out[path.stem] = data
    return out


def rebuild_master(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = sorted(
        [dict(r) for r in rows],
        key=lambda r: (
            -float((r.get("headline") or {}).get("accuracy") or 0.0),
            -int((r.get("headline") or {}).get("hits") or 0),
            str(r.get("experiment_id") or ""),
        ),
    )
    # Collect family labels
    family_labels: List[str] = []
    seen: set = set()
    for r in ranked:
        for lab in ((r.get("headline") or {}).get("by_resource") or {}):
            if lab not in seen:
                seen.add(lab)
                family_labels.append(lab)

    fieldnames = [
        "rank",
        "experiment_id",
        "hits",
        "scorable",
        "accuracy",
        "notes",
        *[ax["key"] for ax in AXES],
        *[f"fam::{lab}" for lab in family_labels],
    ]
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    with MASTER_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for i, r in enumerate(ranked, 1):
            h = r.get("headline") or {}
            vec = r.get("axis_vector") or {}
            row: Dict[str, Any] = {
                "rank": i,
                "experiment_id": r.get("experiment_id"),
                "hits": h.get("hits"),
                "scorable": h.get("scorable"),
                "accuracy": h.get("accuracy"),
                "notes": "; ".join(r.get("notes") or []),
            }
            for ax in AXES:
                row[ax["key"]] = vec.get(ax["key"])
            by = h.get("by_resource") or {}
            for lab in family_labels:
                b = by.get(lab) or {}
                row[f"fam::{lab}"] = (
                    f"{b.get('hits')}/{b.get('scorable')}" if b else ""
                )
            w.writerow(row)

    # comparison.md with preamble + top table
    write_axes_preamble(GRID_COMPARISON_MD, completed=len(ranked))
    lines = GRID_COMPARISON_MD.read_text().rstrip() + "\n\n"
    lines += (
        "| rank | id | accuracy | hits/scorable | flags | notes |\n"
        "|---:|---|---:|---:|---|---|\n"
    )
    for i, r in enumerate(ranked[:50], 1):
        h = r.get("headline") or {}
        flags = r.get("flags") or {}
        flag_s = ", ".join(f"{k}={v}" for k, v in sorted(flags.items())) or "(none)"
        notes = "; ".join(r.get("notes") or []) or "—"
        lines += (
            f"| {i} | `{r.get('experiment_id')}` | {h.get('accuracy')} | "
            f"{h.get('hits')}/{h.get('scorable')} | `{flag_s}` | {notes} |\n"
        )
    if len(ranked) > 50:
        lines += f"\n_… {len(ranked) - 50} more rows in `master.csv`_\n"
    # Per-family for top 10
    if family_labels and ranked:
        lines += "\n## Top-10 per-family\n\n"
        lines += (
            "| rank | id | "
            + " | ".join(f"`{lab}`" for lab in family_labels)
            + " |\n"
        )
        lines += "|---:|---|" + "|".join(["---:"] * len(family_labels)) + "|\n"
        for i, r in enumerate(ranked[:10], 1):
            by = (r.get("headline") or {}).get("by_resource") or {}
            cells = []
            for lab in family_labels:
                b = by.get(lab) or {}
                if not b:
                    cells.append("—")
                else:
                    cells.append(f"{b.get('hits')}/{b.get('scorable')}")
            lines += f"| {i} | `{r.get('experiment_id')}` | " + " | ".join(cells) + " |\n"
    lines += f"\n_Updated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}_\n"
    GRID_COMPARISON_MD.write_text(lines)

    # Pointer summary in parent comparison.md
    top = ranked[:5] if ranked else []
    summary_lines = [
        "# OIE experiment comparison (exhaustive switch grid)",
        "",
        f"Full factorial grid: **{len(ranked)} / {total_combos()}** completed.",
        f"Artifacts: `tmp/oie_owasp_eval/experiments/grid/` "
        f"(`master.csv`, `comparison.md`, per-combo `g_*.json`).",
        "",
        "## Top 5 (canonical gold, agentic excluded)",
        "",
        "| rank | id | accuracy | hits/scorable | axis vector |",
        "|---:|---|---:|---:|---|",
    ]
    for i, r in enumerate(top, 1):
        h = r.get("headline") or {}
        vec = r.get("axis_vector") or {}
        vec_s = ", ".join(f"{k}={v}" for k, v in vec.items())
        summary_lines.append(
            f"| {i} | `{r.get('experiment_id')}` | {h.get('accuracy')} | "
            f"{h.get('hits')}/{h.get('scorable')} | `{vec_s}` |"
        )
    summary_lines.extend(
        [
            "",
            "## Axes / combo count",
            "",
            f"See [grid/comparison.md](grid/comparison.md). "
            f"N = {total_combos()}.",
            "",
            f"_Updated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}_",
            "",
        ]
    )
    COMPARISON_MD.write_text("\n".join(summary_lines))
    return ranked


def promote_winners(ranked: Sequence[Mapping[str, Any]]) -> None:
    if not ranked:
        return
    best = ranked[0]
    h = best.get("headline") or {}
    vec = best.get("axis_vector") or {}
    flags = best.get("flags") or {}
    yaml_flags: Dict[str, str] = {}
    for k, v in flags.items():
        if k in ("CRE_LIBRARIAN_HYBRID_BETA", "CRE_LIBRARIAN_HYBRID_GAMMA"):
            if vec.get("hybrid") == "nameheavy":
                yaml_flags[k] = str(v)
            continue
        if k == "CRE_LIBRARIAN_MARGIN_GAMMA":
            yaml_flags[k] = str(v)
            continue
        if str(v) in ("1", "true", "True"):
            yaml_flags[k] = "1"

    if yaml_flags:
        flag_block = "".join(f'  {k}: "{v}"\n' for k, v in sorted(yaml_flags.items()))
        flags_section = "flags:\n" + flag_block
    else:
        flags_section = "flags: {}\n"
    STACK_YAML.write_text(
        "experiment_id: stack_winners\n"
        "description: >\n"
        f"  Exhaustive switch grid winner ({datetime.now(timezone.utc).date()}): "
        f"{best.get('experiment_id')} → {h.get('hits')}/{h.get('scorable')} "
        f"({h.get('accuracy')}). Full factorial over retrieval/precision toggles; "
        "trained CE deferred. No live Links writes.\n"
        f"{flags_section}"
        "include_agentic: false\n"
    )

    top5 = ranked[:5]
    body = [
        "# OIE experiment winners (exhaustive switch grid)",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "**Worktree:** `OpenCRE-wt-oie-1088-harness`",
        f"**Shared pipeline knowledge:** `{RUN_ID}` "
        "(Module C re-run per combo; CE on CPU; shortlist judge off — "
        "Gemini hangs blocked judge-ON factorial)",
        "**Gold:** canonical (`local_gold: false`); Agentic stub excluded",
        f"**Grid:** {len(ranked)} / {total_combos()} combos "
        f"(see `tmp/oie_owasp_eval/experiments/grid/`)",
        "",
        "## Best combo",
        "",
        f"- **id:** `{best.get('experiment_id')}`",
        f"- **score:** {h.get('hits')}/{h.get('scorable')} ({h.get('accuracy')})",
        f"- **axes:** `{json.dumps(vec)}`",
        f"- **env flags:** `{json.dumps(flags)}`",
        "",
        "## Top 5",
        "",
        "| rank | id | hits/scorable | accuracy | notes |",
        "|---:|---|---:|---:|---|",
    ]
    for i, r in enumerate(top5, 1):
        hh = r.get("headline") or {}
        notes = "; ".join(r.get("notes") or []) or "—"
        body.append(
            f"| {i} | `{r.get('experiment_id')}` | "
            f"{hh.get('hits')}/{hh.get('scorable')} | {hh.get('accuracy')} | {notes} |"
        )
    body.extend(
        [
            "",
            "## Promoted stack_winners.yaml flags",
            "",
            "```",
            yaml.safe_dump({"flags": yaml_flags}, default_flow_style=False).rstrip(),
            "```",
            "",
            "## No-ops / caveats",
            "",
            "- `USE_RRF=1` without `DUAL_INDEX=1` is a no-op "
            "(copied from rrf=0 sibling; still in master.csv).",
            "- ASVS5 harvest still excluded (chapter HTML OOM); not in denominator.",
            "- Trained CE deferred — not in this grid.",
            "- `SHORTLIST_JUDGE=0` fixed (Gemini judge hangs blocked judge-ON factorial).",
            "",
            "## Parallel Module C (isolated DBs)",
            "",
            "4 workers × `cre_grid_w0`…`cre_grid_w3` (~500MB TEMPLATE clones of `cre`).",
            "",
            "```bash",
            "WORKERS=4 scripts/oie_owasp_eval/clone_grid_worker_dbs.sh",
            "python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py "
            "--workers 4 --clone",
            "# re-attach aggregator if it exits while workers keep running:",
            "python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py "
            "--monitor-only",
            "```",
            "",
            "Do not write live Links from this matrix.",
            "",
        ]
    )
    WINNERS_MD.write_text("\n".join(body))


def combo_id_from_vector(vector: Mapping[str, Any]) -> str:
    """Build stable combo id from axis vector tags."""
    return (
        "g_"
        + "_".join(
            [
                str(vector["cre_summary"]),
                str(vector["dual_index"]),
                str(vector["use_rrf"]),
                str(vector["context_enrich"]),
                str(vector["margin_gamma"]),
                str(vector["hub_leaf_cage"]),
                str(vector["focus_query"]),
                str(vector["hybrid"]),
                str(vector["cre_text_enrich"]),
            ]
        )
    )


def sibling_rrf_off_id(combo_id: str, vector: Mapping[str, Any]) -> Optional[str]:
    """If this combo is RRF-without-dual, return the id with use_rrf=0."""
    if vector.get("use_rrf") != "1" or vector.get("dual_index") != "0":
        return None
    off = dict(vector)
    off["use_rrf"] = "0"
    return combo_id_from_vector(off)


def rrf_on_twin_id(vector: Mapping[str, Any]) -> Optional[str]:
    """If dual=0 and rrf=0, return the pure-noop twin with use_rrf=1."""
    if vector.get("dual_index") != "0" or vector.get("use_rrf") != "0":
        return None
    on = dict(vector)
    on["use_rrf"] = "1"
    return combo_id_from_vector(on)


def copy_noop_from(
    combo_id: str,
    flags: Dict[str, str],
    vector: Dict[str, Any],
    notes: List[str],
    source: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Clone a scored sibling for known no-op flag vectors (no Module C)."""
    if not claim_combo(combo_id):
        return None
    payload = dict(source)
    payload["experiment_id"] = combo_id
    payload["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["axis_vector"] = vector
    payload["flags"] = flags
    payload["notes"] = list(notes) + [
        f"copied_noop_from={source.get('experiment_id')}"
    ]
    payload["elapsed_sec"] = 0.0
    payload["copied_from"] = source.get("experiment_id")
    payload["status"] = source.get("status") or "ok"
    # Do not copy b2_report bytes; headline already in json.
    write_combo_json_atomic(combo_id, payload)
    print(
        f"NOOP_COPY {combo_id} <- {source.get('experiment_id')} "
        f"{(payload.get('headline') or {}).get('hits')}/"
        f"{(payload.get('headline') or {}).get('scorable')}",
        flush=True,
    )
    return payload


def run_one(combo_id: str, flags: Dict[str, str], vector: Dict[str, Any], notes: List[str]) -> Dict[str, Any]:
    t0 = time.time()
    conn = parse_db_url()
    print(f"======== {combo_id} db={conn['dbname']} ========", flush=True)
    print(f"flags {flags}", flush=True)
    reset_queues()
    mc = run_module_c(flags)
    b2_path = GRID_DIR / f"{combo_id}.b2_report.json"
    scored = score_b2(b2_path)
    elapsed = round(time.time() - t0, 1)
    payload: Dict[str, Any] = {
        "experiment_id": combo_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": RUN_ID,
        "worker_db": conn["dbname"],
        "local_gold": False,
        "exclude_agentic_from_headline": True,
        "axis_vector": vector,
        "flags": flags,
        "notes": notes,
        "fixed_env": FIXED_ENV,
        "module_c": {
            "config": mc.get("config"),
            "summary": {
                k: (mc.get("summary") or {}).get(k)
                for k in (
                    "decisions_total",
                    "linked",
                    "review_required",
                    "errors",
                    "consumed",
                )
                if isinstance(mc.get("summary"), dict)
            },
        },
        "elapsed_sec": elapsed,
        "status": scored.get("status"),
        "b2": None,
        "headline": None,
        "asvs5": {
            "status": "blocked",
            "reason": "excluded from B2 harvest (chapter HTML OOMs Module C)",
        },
    }
    if scored.get("status") == "ok":
        report = scored["report"]
        payload["b2"] = {
            "status": "ok",
            "report_path": str(b2_path.relative_to(ROOT)),
            "hits": report.get("hits"),
            "scorable": report.get("scorable"),
            "accuracy": report.get("accuracy"),
            "by_resource": report.get("by_resource"),
        }
        payload["headline"] = headline_from_b2(report)
        print(
            f"RESULT {combo_id} "
            f"{payload['headline']['hits']}/{payload['headline']['scorable']} "
            f"({payload['headline']['accuracy']}) in {elapsed}s",
            flush=True,
        )
    else:
        payload["b2"] = {"status": "failed", "returncode": scored.get("returncode")}
        print(f"FAIL {combo_id} rc={scored.get('returncode')}", flush=True)
    write_combo_json_atomic(combo_id, payload)
    return payload


def refresh_artifacts_locked(completed_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Rebuild master/comparison/winners under mkdir lock (parallel-safe)."""
    if not try_acquire_artifacts_lock():
        print("ARTIFACTS_LOCK_BUSY skipping rebuild", flush=True)
        return []
    try:
        ranked = rebuild_master(completed_rows)
        promote_winners(ranked)
        return ranked
    finally:
        release_artifacts_lock()


def write_state(
    *,
    completed: int,
    total: int,
    last: str,
    module_c_runs: int = 0,
    noop_copied: int = 0,
    worker_id: Optional[int] = None,
    workers: Optional[int] = None,
    status: str = "in_progress",
) -> None:
    payload: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed": completed,
        "total": total,
        "last": last,
        "module_c_runs": module_c_runs,
        "noop_copied": noop_copied,
        "status": status,
    }
    if worker_id is not None:
        payload["worker_id"] = worker_id
    if workers is not None:
        payload["workers"] = workers
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-count", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N new combos")
    parser.add_argument("--only", nargs="*", default=[], help="Only these combo ids")
    parser.add_argument("--refresh-only", action="store_true", help="Rebuild CSV/md only")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if combo json exists",
    )
    parser.add_argument(
        "--worker-id",
        type=int,
        default=None,
        help="0-based worker index; with --workers, shard combo indices",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Total parallel workers (default 1 = sequential)",
    )
    parser.add_argument(
        "--skip-artifacts",
        action="store_true",
        help="Do not rebuild master.csv/comparison/winners (aggregator does it)",
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=None,
        help="Override Postgres database name (sets DEV_DATABASE_URL host/user defaults)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    os.chdir(ROOT)
    if args.db_name:
        os.environ["DEV_DATABASE_URL"] = (
            f"postgresql://cre:password@127.0.0.1:5432/{args.db_name}"
        )
    os.environ.setdefault("DEV_DATABASE_URL", DEFAULT_DB_URL)
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("PYTHONPATH", str(ROOT))
    os.environ.setdefault(
        "CRE_LIBRARIAN_CRE_SUMMARY_CACHE", str(ROOT / "tmp" / "oie_cre_summaries")
    )
    for k, v in FIXED_ENV.items():
        os.environ.setdefault(k, v)

    workers = max(1, int(args.workers or 1))
    worker_id = args.worker_id
    if worker_id is not None and not (0 <= worker_id < workers):
        print(f"BAD_WORKER_ID {worker_id} workers={workers}", flush=True)
        return 2
    skip_artifacts = bool(args.skip_artifacts) or (
        worker_id is not None and workers > 1
    )

    GRID_DIR.mkdir(parents=True, exist_ok=True)
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    n = total_combos()
    conn = parse_db_url()
    print(
        f"GRID_TOTAL={n} worker={worker_id}/{workers} db={conn['dbname']} "
        f"skip_artifacts={skip_artifacts}",
        flush=True,
    )
    if worker_id is None:
        write_axes_preamble(GRID_COMPARISON_MD, completed=0)
        COMPARISON_MD.write_text(
            "# OIE experiment comparison (exhaustive switch grid)\n\n"
            f"Starting full factorial: **0 / {n}**.\n\n"
            "Axes documented in `grid/comparison.md`.\n"
        )

    if args.dry_run_count:
        for i, (cid, flags, vec, notes) in enumerate(iter_combos(), 1):
            if i <= 3 or i == n:
                print(i, cid, vec, notes)
        print(f"TOTAL={n}")
        return 0

    if args.refresh_only:
        completed = list(load_completed().values())
        ranked = refresh_artifacts_locked(completed)
        print(f"REFRESHed {len(completed)} rows ranked={len(ranked)}", flush=True)
        return 0

    completed_map = load_completed()
    print(f"RESUME already_ok={len(completed_map)}", flush=True)
    ran = 0
    noop_copied = 0
    only = set(args.only or [])

    def _write_state(last: str) -> None:
        # Always re-scan disk so parallel workers see each other's progress.
        done = len(load_completed())
        write_state(
            completed=done,
            total=n,
            last=last,
            module_c_runs=ran,
            noop_copied=noop_copied,
            worker_id=worker_id,
            workers=workers if worker_id is not None else None,
        )

    def _maybe_rebuild() -> None:
        if skip_artifacts:
            return
        # Refresh map from disk before rebuild (noop twins from other workers).
        fresh = load_completed()
        completed_map.clear()
        completed_map.update(fresh)
        refresh_artifacts_locked(list(completed_map.values()))

    def _try_noop_copy(
        combo_id: str,
        flags: Dict[str, str],
        vector: Dict[str, Any],
        notes: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Instant-copy RRF-without-dual from rrf=0 sibling when available."""
        sib = sibling_rrf_off_id(combo_id, vector)
        if not sib:
            return None
        # Sibling may have been written by another worker — re-read disk.
        if sib not in completed_map:
            completed_map.update(load_completed())
        if sib not in completed_map:
            return None
        return copy_noop_from(combo_id, flags, vector, notes, completed_map[sib])

    def _in_shard(combo_index: int) -> bool:
        if worker_id is None or workers <= 1:
            return True
        return (combo_index % workers) == worker_id

    # Eager pass: materialize every RRF-without-dual noop whose sibling is done.
    # All workers may attempt (claim_combo serializes); keeps noops off Module C.
    if not args.force:
        eager = 0
        for combo_id, flags, vector, notes in iter_combos():
            if only and combo_id not in only:
                continue
            if combo_id in completed_map:
                continue
            payload = _try_noop_copy(combo_id, flags, vector, notes)
            if payload is None:
                continue
            completed_map[combo_id] = payload
            noop_copied += 1
            eager += 1
        if eager:
            _maybe_rebuild()
            _write_state(f"eager_noop×{eager}")
            print(
                f"EAGER_NOOP_COPY count={eager} completed={len(load_completed())}",
                flush=True,
            )

    try:
        for combo_index, (combo_id, flags, vector, notes) in enumerate(iter_combos()):
            if only and combo_id not in only:
                continue
            if not args.force and combo_id in completed_map:
                continue
            # Known no-op: any worker may copy (claim); do not require shard.
            is_rrf_noop = (
                vector.get("use_rrf") == "1" and vector.get("dual_index") == "0"
            )
            if not is_rrf_noop and not _in_shard(combo_index):
                continue
            # Re-check disk (another worker may have finished this id).
            if not args.force:
                completed_map.update(load_completed())
                if combo_id in completed_map:
                    continue

            payload = None if args.force else _try_noop_copy(
                combo_id, flags, vector, notes
            )
            if payload is not None:
                completed_map[combo_id] = payload
                noop_copied += 1
            else:
                if is_rrf_noop and not args.force:
                    # Sibling not ready yet; shard owner of twin will copy later,
                    # or we skip until sibling lands. Do not Module-C a known noop.
                    continue
                if not _in_shard(combo_index):
                    continue
                if not claim_combo(combo_id):
                    print(f"SKIP_CLAIMED {combo_id}", flush=True)
                    continue
                try:
                    payload = run_one(combo_id, flags, vector, notes)
                except Exception:  # noqa: BLE001 — keep walking the grid
                    traceback.print_exc()
                    print(f"COMBO_FAIL {combo_id}", flush=True)
                    release_combo_claim(combo_id)
                    ran += 1
                    continue
                if payload.get("status") == "ok":
                    completed_map[combo_id] = payload
                    twin_id = rrf_on_twin_id(vector)
                    if twin_id and twin_id not in completed_map and (
                        not only or twin_id in only
                    ):
                        twin_vec = dict(vector)
                        twin_vec["use_rrf"] = "1"
                        twin_flags = dict(flags)
                        twin_flags["CRE_LIBRARIAN_USE_RRF"] = "1"
                        twin_notes = list(notes) + [
                            "noop: USE_RRF without DUAL_INDEX"
                        ]
                        twin_payload = copy_noop_from(
                            twin_id,
                            twin_flags,
                            twin_vec,
                            twin_notes,
                            payload,
                        )
                        if twin_payload is not None:
                            completed_map[twin_id] = twin_payload
                            noop_copied += 1
                else:
                    # Failed score — release claim so resume can retry.
                    release_combo_claim(combo_id)
                ran += 1
            _maybe_rebuild()
            _write_state(combo_id)
            if args.limit and ran >= args.limit:
                print(f"LIMIT reached ({args.limit})", flush=True)
                break
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        if not skip_artifacts:
            refresh_artifacts_locked(list(load_completed().values()))
        print("GRID_PARTIAL_FAIL", flush=True)
        return 1

    if not skip_artifacts:
        refresh_artifacts_locked(list(load_completed().values()))
    done = len(load_completed())
    write_state(
        completed=done,
        total=n,
        last="worker_done" if worker_id is not None else "GRID_DONE",
        module_c_runs=ran,
        noop_copied=noop_copied,
        worker_id=worker_id,
        workers=workers if worker_id is not None else None,
        status="done" if done >= n else "in_progress",
    )
    print(
        f"GRID_DONE completed={done}/{n} newly_ran={ran} noop_copied={noop_copied} "
        f"worker={worker_id}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
