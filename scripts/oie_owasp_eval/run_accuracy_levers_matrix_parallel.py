#!/usr/bin/env python3
"""Launch N isolated DB workers for the accuracy-levers matrix.

Why not 20: each Module C process loads ~2GB (cross-encoder + hub). A 36GB
laptop can spare ~4 without swapping. Gemini already 429s under one worker —
more workers need retry backoff, not a stampede.

Provisions ``cre_al_w0``…``cre_al_w{N-1}`` via TEMPLATE clone of ``cre``
(requires terminating other sessions on ``cre``), then spawns one matrix shard
per clone. Skips combo JSON that already has ``status=ok``.

Usage:
  PYTHONPATH=. python scripts/oie_owasp_eval/run_accuracy_levers_matrix_parallel.py \\
    --run-id orch-al-20261011T115344Z --workers 4

  # after workers finish (or while they run):
  PYTHONPATH=. python scripts/oie_owasp_eval/run_accuracy_levers_matrix.py --matrix-only
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tmp" / "oie_owasp_eval" / "experiments" / "accuracy_levers"
CLONE_SH = ROOT / "scripts" / "oie_owasp_eval" / "clone_grid_worker_dbs.sh"
MATRIX_PY = ROOT / "scripts" / "oie_owasp_eval" / "run_accuracy_levers_matrix.py"
DEFAULT_RUN = "orch-al-20261011T115344Z"
PREFIX = "cre_al_w"


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


def clone_dbs(workers: int, *, force: bool) -> None:
    env = os.environ.copy()
    env["WORKERS"] = str(workers)
    env["DB_PREFIX"] = PREFIX
    env["SOURCE_DB"] = env.get("SOURCE_DB", "cre")
    if force:
        env["FORCE"] = "1"
    print(
        f"cloning {workers} DBs PREFIX={PREFIX} FORCE={env.get('FORCE', '0')}",
        flush=True,
    )
    subprocess.run(["zsh", str(CLONE_SH)], cwd=str(ROOT), env=env, check=True)


def spawn_workers(run_id: str, workers: int) -> List[subprocess.Popen]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    procs: List[subprocess.Popen] = []
    for i in range(workers):
        db = f"postgresql://cre:password@127.0.0.1:5432/{PREFIX}{i}"
        log = OUT_DIR / f"worker_{i}.log"
        env = os.environ.copy()
        env["DEV_DATABASE_URL"] = db
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["NO_LOAD_GRAPH_DB"] = "1"
        env["FLASK_CONFIG"] = "development"
        # Soften stampede on Gemini a bit per worker.
        env.setdefault("CRE_LLM_RETRY_SLEEP_SECONDS", "20")
        cmd = [
            sys.executable,
            "-u",
            str(MATRIX_PY),
            "--run-id",
            run_id,
            "--workers",
            str(workers),
            "--worker-id",
            str(i),
        ]
        handle = open(log, "w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        procs.append(proc)
        print(f"spawned worker={i} pid={proc.pid} db={PREFIX}{i} log={log}", flush=True)
    return procs


def wait_and_aggregate(procs: Sequence[subprocess.Popen]) -> int:
    rc = 0
    while True:
        alive = [p for p in procs if p.poll() is None]
        done = sum(
            1
            for p in OUT_DIR.glob("al_*.json")
            if not p.name.endswith(".b2.json")
            and '"status": "ok"' in p.read_text(errors="ignore")[:200]
        )
        # recount properly
        ok = 0
        for p in OUT_DIR.glob("al_*.json"):
            if p.name.endswith(".b2.json"):
                continue
            try:
                import json

                if json.loads(p.read_text()).get("status") == "ok":
                    ok += 1
            except Exception:
                pass
        print(
            f"aggregate alive={len(alive)}/{len(procs)} completed_ok={ok}/16",
            flush=True,
        )
        subprocess.run(
            [sys.executable, str(MATRIX_PY), "--matrix-only"],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            check=False,
        )
        if not alive:
            break
        time.sleep(60)
    for p in procs:
        if p.returncode not in (0, None):
            rc = p.returncode or rc
    return rc


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel Module C workers / DB clones (default 4; not 20)",
    )
    parser.add_argument(
        "--skip-clone",
        action="store_true",
        help="Reuse existing cre_al_w* databases",
    )
    parser.add_argument(
        "--force-clone",
        action="store_true",
        help="DROP and recreate worker DBs from TEMPLATE cre",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _load_dotenv()
    workers = max(1, min(int(args.workers), 8))  # hard cap: laptop RAM
    if int(args.workers) > 8:
        print(
            f"clamping workers {args.workers} → {workers} (Module C ~2GB RSS each)",
            flush=True,
        )

    if not args.skip_clone:
        clone_dbs(workers, force=args.force_clone)

    procs = spawn_workers(args.run_id.strip(), workers)
    return wait_and_aggregate(procs)


if __name__ == "__main__":
    raise SystemExit(main())
