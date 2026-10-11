#!/usr/bin/env python3
"""16-combo matrix for experimental accuracy levers on B2 gold (+ ASVS5).

Baseline = promoted librarian stack (SHORTLIST_JUDGE on). Axes (default off):

  CRE_LIBRARIAN_PAIRWISE_VOTE
  CRE_LIBRARIAN_SOURCE_GROUNDING
  CRE_LIBRARIAN_CROSSWALK_CAGE
  CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED

Reuses a shared B2 harvest (Module A+B keep-all), then clears decisions and
re-runs Module C per combo. Scores via ``run_b2_pr_mappings.py --score-only``
including ASVS 5.0 provisional; excludes agentic stub from headline.

Parallel: shard combos with ``--workers N --worker-id I`` on **isolated DB
clones** (``knowledge_queue.content_hash`` is globally unique — same-DB KQ
clones collide). Prefer
``scripts/oie_owasp_eval/run_accuracy_levers_matrix_parallel.py --workers 4``.

Usage:
  # Fresh harvest + full matrix (slow; needs Postgres + LLM keys):
  PYTHONPATH=. python scripts/oie_owasp_eval/run_accuracy_levers_matrix.py \\
    --harvest

  # Reuse existing run_id knowledge_queue:
  PYTHONPATH=. python scripts/oie_owasp_eval/run_accuracy_levers_matrix.py \\
    --run-id orch-b2-YYYYMMDDTHHMMSSZ

  # One shard of a parallel run (DB clone already provisioned):
  DEV_DATABASE_URL=postgresql://cre:password@127.0.0.1:5432/cre_al_w0 \\
    PYTHONPATH=. python scripts/oie_owasp_eval/run_accuracy_levers_matrix.py \\
      --run-id orch-al-… --workers 4 --worker-id 0

Writes:
  tmp/oie_owasp_eval/experiments/accuracy_levers/<combo>.json
  tmp/oie_owasp_eval/experiments/accuracy_levers/matrix.md
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"
OUT_DIR = ART / "experiments" / "accuracy_levers"
LOCKS_DIR = OUT_DIR / ".locks"
DEFAULT_DB = "postgresql://cre:password@127.0.0.1:5432/cre"

AXES: Tuple[Tuple[str, str], ...] = (
    ("pairwise", "CRE_LIBRARIAN_PAIRWISE_VOTE"),
    ("grounding", "CRE_LIBRARIAN_SOURCE_GROUNDING"),
    ("crosswalk", "CRE_LIBRARIAN_CROSSWALK_CAGE"),
    ("coverage", "CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED"),
)

PROMOTED: Dict[str, str] = {
    "CRE_LIBRARIAN_CRE_SUMMARY": "1",
    "CRE_LIBRARIAN_MARGIN_GAMMA": "0.85",
    "CRE_LIBRARIAN_DUAL_INDEX": "1",
    "CRE_LIBRARIAN_SHORTLIST_JUDGE": "1",
    "CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS": "3",
    "CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP": "8",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN": "1",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS": "20",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB": "0",
    "CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST": "0",
    "CRE_LIBRARIAN_RETRIEVER_BACKEND": "pgvector",
    "CRE_LIBRARIAN_DEVICE": "cpu",
    "NO_LOAD_GRAPH_DB": "1",
}

AGENTIC = "OWASP Agentic AI (stub, no hub Links)"
EXCLUDE_ALWAYS = ("owasp_agentic_ai_stub",)


def _load_dotenv() -> None:
    for env_path in (ROOT / ".env", ROOT / "tmp" / "oie.env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def parse_db_url(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    db = (parsed.path or "/cre").lstrip("/") or "cre"
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "cre",
        "password": parsed.password or os.environ.get("PGPASSWORD", "password"),
        "dbname": db,
        "url": url,
    }


def combo_id(bits: Mapping[str, str]) -> str:
    parts = [f"{k}{bits[k]}" for k, _ in AXES]
    return "al_" + "_".join(parts)


def all_combos() -> List[Tuple[str, Dict[str, str]]]:
    keys = [a[0] for a in AXES]
    envs = [a[1] for a in AXES]
    out: List[Tuple[str, Dict[str, str]]] = []
    for vals in itertools.product(("0", "1"), repeat=len(AXES)):
        bits = dict(zip(keys, vals))
        env = {e: v for e, v in zip(envs, vals)}
        out.append((combo_id(bits), env))
    return out


def reset_queues(run_id: str, db_url: str) -> None:
    conn = parse_db_url(db_url)
    sql = (
        f"DELETE FROM decision_queue WHERE pipeline_run_id = '{run_id}'; "
        f"UPDATE knowledge_queue SET consumed_at = NULL "
        f"WHERE pipeline_run_id = '{run_id}';"
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


def harvest(run_id: str) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"),
        "--run-id",
        run_id,
        "--keep-all-knowledge",
        "--exclude-fixtures",
        *EXCLUDE_ALWAYS,
        "--out",
        str(OUT_DIR / f"{run_id}.harvest_b2.json"),
    ]
    env = os.environ.copy()
    env.update(PROMOTED)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # Harvest baseline with all experimental levers off.
    for _, flag in AXES:
        env[flag] = "0"
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"harvest failed rc={proc.returncode}")


def run_module_c(run_id: str, lever_env: Mapping[str, str]) -> Dict[str, Any]:
    from application.cmd.cre_main import db_connect
    from application.utils.librarian.config_loader import load_config
    from application.utils.librarian.envelope_sink import DbEnvelopeSink
    from application.utils.librarian.factory import build_components
    from application.utils.librarian.queue_runner import run_librarian_queue

    for k, v in PROMOTED.items():
        os.environ[k] = v
    for k, v in lever_env.items():
        os.environ[k] = v
    # Clear force-off for unused leaf force.
    os.environ.pop("CRE_LIBRARIAN_LEAF_DRILLDOWN_FORCE_RESOURCES", None)

    cfg = load_config()
    database = db_connect(path=os.environ["DEV_DATABASE_URL"])
    components = build_components(database, config=cfg)
    sink = DbEnvelopeSink(database.session, run_id)
    summary = run_librarian_queue(
        database.session,
        run_id,
        components,
        cfg,
        at=datetime.now(timezone.utc),
        sink=sink,
        dry_run=False,
    )
    database.session.commit()
    return summary if isinstance(summary, dict) else {"raw": str(summary)}


def score_b2(run_id: str, out_path: Path) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "oie_owasp_eval" / "run_b2_pr_mappings.py"),
        "--score-only",
        "--run-id",
        run_id,
        "--out",
        str(out_path),
        "--exclude-fixtures",
        *EXCLUDE_ALWAYS,
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    if proc.returncode != 0 or not out_path.is_file():
        return {"status": "failed", "returncode": proc.returncode}
    return {"status": "ok", "report": json.loads(out_path.read_text())}


def headline(report: Mapping[str, Any]) -> Dict[str, Any]:
    by_resource = dict(report.get("by_resource") or {})
    hits = scorable = 0
    families: Dict[str, Any] = {}
    for label, bucket in by_resource.items():
        if label == AGENTIC:
            continue
        families[label] = {
            "hits": bucket.get("hits"),
            "scorable": bucket.get("scorable"),
            "accuracy": bucket.get("accuracy"),
        }
        hits += int(bucket.get("hits") or 0)
        scorable += int(bucket.get("scorable") or 0)
    return {
        "hits": hits,
        "scorable": scorable,
        "accuracy": round((hits / scorable) if scorable else 0.0, 4),
        "by_resource": families,
    }


def _lock_owner_alive(lock: Path) -> bool:
    try:
        pid = int((lock / "pid").read_text().strip() or 0)
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def claim_combo(combo_id: str, *, force: bool = False) -> bool:
    """mkdir flock so parallel workers never run the same combo."""
    out = OUT_DIR / f"{combo_id}.json"
    if out.is_file() and not force:
        try:
            data = json.loads(out.read_text())
            if data.get("status") == "ok" and data.get("headline"):
                return False
        except (json.JSONDecodeError, OSError):
            pass
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock = LOCKS_DIR / combo_id
    if lock.is_dir() and not _lock_owner_alive(lock):
        release_combo_claim(combo_id)
    try:
        lock.mkdir()
        (lock / "pid").write_text(f"{os.getpid()}\n")
        return True
    except FileExistsError:
        return False


def release_combo_claim(combo_id: str) -> None:
    lock = LOCKS_DIR / combo_id
    if not lock.is_dir():
        return
    try:
        for child in lock.iterdir():
            child.unlink(missing_ok=True)
        lock.rmdir()
    except OSError:
        pass


def load_completed_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(OUT_DIR.glob("al_*.json")):
        if path.name.endswith(".b2.json"):
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") == "ok":
            rows.append(data)
    return rows


def write_matrix_md(rows: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# Accuracy levers matrix",
        "",
        "Promoted stack baseline + four experimental fail-closed levers.",
        "Gold: B2 harnesses including ASVS 5.0 provisional; agentic stub excluded.",
        "",
        "| combo | pairwise | grounding | crosswalk | coverage | exact hits | scorable | accuracy |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for r in rows:
        h = r.get("headline") or {}
        v = r.get("levers") or {}
        lines.append(
            "| `{id}` | {p} | {g} | {c} | {v} | {hits} | {sc} | {acc:.1%} |".format(
                id=r.get("combo_id"),
                p=v.get("CRE_LIBRARIAN_PAIRWISE_VOTE", "?"),
                g=v.get("CRE_LIBRARIAN_SOURCE_GROUNDING", "?"),
                c=v.get("CRE_LIBRARIAN_CROSSWALK_CAGE", "?"),
                v=v.get("CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED", "?"),
                hits=h.get("hits", 0),
                sc=h.get("scorable", 0),
                acc=float(h.get("accuracy") or 0.0),
            )
        )
    (OUT_DIR / "matrix.md").write_text("\n".join(lines) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="", help="Existing B2 pipeline_run_id")
    parser.add_argument(
        "--harvest",
        action="store_true",
        help="Run fresh B2 harvest (keep-all) before the matrix",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Optional combo_id filter (e.g. al_pairwise0_grounding0_crosswalk0_coverage0)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing JSON")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Total parallel workers (shard combos; default 1 = sequential)",
    )
    parser.add_argument(
        "--worker-id",
        type=int,
        default=None,
        help="0-based worker index; with --workers>1, claim-sharded combos",
    )
    parser.add_argument(
        "--matrix-only",
        action="store_true",
        help="Rebuild matrix.md from on-disk combo JSON and exit",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _load_dotenv()
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("DEV_DATABASE_URL", DEFAULT_DB)
    db_url = os.environ["DEV_DATABASE_URL"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.matrix_only:
        rows = load_completed_rows()
        rows.sort(key=lambda r: str(r.get("combo_id") or ""))
        write_matrix_md(rows)
        print(
            f"wrote {OUT_DIR / 'matrix.md'} completed={len(rows)}/16",
            flush=True,
        )
        return 0

    workers = max(1, int(args.workers or 1))
    worker_id = args.worker_id
    if worker_id is not None and not (0 <= worker_id < workers):
        print(f"BAD_WORKER_ID {worker_id} workers={workers}", flush=True)
        return 2

    run_id = (args.run_id or "").strip()
    if args.harvest or not run_id:
        if worker_id is not None and workers > 1:
            print(
                "harvest must run once on the source DB before parallel workers",
                file=sys.stderr,
            )
            return 2
        run_id = run_id or (
            "orch-al-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        print(f"harvesting run_id={run_id}", flush=True)
        harvest(run_id)
    else:
        print(f"reusing run_id={run_id}", flush=True)

    only = {str(s).strip() for s in (args.only or []) if str(s).strip()}
    combos = all_combos()
    if worker_id is not None and workers > 1:
        combos = [c for idx, c in enumerate(combos) if idx % workers == worker_id]
        print(
            f"worker={worker_id}/{workers} db={parse_db_url(db_url)['dbname']} "
            f"shard_combos={len(combos)}",
            flush=True,
        )

    rows: List[Dict[str, Any]] = []
    for cid, lever_env in combos:
        if only and cid not in only:
            continue
        out = OUT_DIR / f"{cid}.json"
        if out.is_file() and not args.force:
            try:
                prev = json.loads(out.read_text())
                if prev.get("status") == "ok":
                    rows.append(prev)
                    print(f"skip {cid} (cached)", flush=True)
                    continue
            except json.JSONDecodeError:
                pass

        if workers > 1 and not claim_combo(cid, force=args.force):
            print(f"skip {cid} (claimed/cached by peer)", flush=True)
            continue

        print(f"combo {cid} …", flush=True)
        try:
            reset_queues(run_id, db_url)
            summary = run_module_c(run_id, lever_env)
            score_path = OUT_DIR / f"{cid}.b2.json"
            scored = score_b2(run_id, score_path)
            if scored.get("status") != "ok":
                payload = {
                    "status": "failed",
                    "combo_id": cid,
                    "levers": lever_env,
                    "run_id": run_id,
                    "worker_id": worker_id,
                    "module_c": summary,
                    "score": scored,
                }
            else:
                payload = {
                    "status": "ok",
                    "combo_id": cid,
                    "levers": lever_env,
                    "run_id": run_id,
                    "worker_id": worker_id,
                    "module_c": summary,
                    "headline": headline(scored["report"]),
                    "b2_report": str(score_path.relative_to(ROOT)),
                }
        except Exception as exc:  # noqa: BLE001
            payload = {
                "status": "error",
                "combo_id": cid,
                "levers": lever_env,
                "run_id": run_id,
                "worker_id": worker_id,
                "error": str(exc),
            }
            release_combo_claim(cid)
        out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        if payload.get("status") == "ok":
            release_combo_claim(cid)
        rows.append(payload)
        h = payload.get("headline") or {}
        print(
            f"  → status={payload.get('status')} "
            f"acc={h.get('accuracy')} hits={h.get('hits')}/{h.get('scorable')}",
            flush=True,
        )

    # Parallel workers: rebuild from all on-disk OK rows (peers included).
    time.sleep(0.2)
    disk_rows = load_completed_rows()
    disk_rows.sort(key=lambda r: str(r.get("combo_id") or ""))
    write_matrix_md(disk_rows)
    print(
        f"wrote {OUT_DIR / 'matrix.md'} completed={len(disk_rows)}/16 "
        f"worker={worker_id}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
