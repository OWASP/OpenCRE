#!/usr/bin/env python3
"""Launch isolated parallel Module C switch-grid workers.

Each worker gets its own Postgres DB (cre_grid_w0 …) cloned from ``cre`` so
decision_queue DELETE/reset never races. Combo JSON writes use mkdir locks in
``grid/.locks/``. This process:

1. Optionally clones worker DBs (``--clone``).
2. Spawns N worker processes (``run_exhaustive_switch_grid.py --worker-id``).
3. Aggregates status → ``grid/_state.json``, ``status.txt``, master/comparison.

Re-attach without respawning::

  python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py --monitor-only

Example::

  python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py \\
    --workers 4 --clone
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
EXP_ART = ROOT / "tmp" / "oie_owasp_eval" / "experiments"
GRID_DIR = EXP_ART / "grid"
STATE_PATH = GRID_DIR / "_state.json"
STATUS_TXT = EXP_ART / "status.txt"
STATUS_LOG = EXP_ART / "status.log"
PARALLEL_DIR = EXP_ART / "parallel"
CLONE_SCRIPT = ROOT / "scripts" / "oie_owasp_eval" / "clone_grid_worker_dbs.sh"
WORKER_SCRIPT = ROOT / "scripts" / "oie_owasp_eval" / "run_exhaustive_switch_grid.py"
DB_PREFIX = "cre_grid_w"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_completed() -> tuple[int, int]:
    sys.path.insert(0, str(ROOT / "scripts" / "oie_owasp_eval"))
    from run_exhaustive_switch_grid import load_completed, total_combos  # noqa: WPS433

    return len(load_completed()), total_combos()


def refresh_artifacts() -> int:
    sys.path.insert(0, str(ROOT / "scripts" / "oie_owasp_eval"))
    from run_exhaustive_switch_grid import (  # noqa: WPS433
        load_completed,
        refresh_artifacts_locked,
        total_combos,
        write_state,
    )

    rows = list(load_completed().values())
    refresh_artifacts_locked(rows)
    n = total_combos()
    write_state(
        completed=len(rows),
        total=n,
        last="aggregator",
        status="done" if len(rows) >= n else "in_progress",
        workers=None,
    )
    return len(rows)


def write_status_line(*, completed: int, total: int, last: str, workers_alive: int) -> None:
    pct = f"{(100.0 * completed / total):.1f}" if total else "0.0"
    line = (
        f"{_iso()}  {completed}/{total} ({pct}%)  last={last}  "
        f"running={'yes' if workers_alive else 'no'}  parallel_workers={workers_alive}"
    )
    STATUS_TXT.write_text(line + "\n")
    with STATUS_LOG.open("a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def clone_dbs(workers: int, force: bool) -> None:
    env = os.environ.copy()
    env["WORKERS"] = str(workers)
    env["FORCE"] = "1" if force else "0"
    env.setdefault("PGPASSWORD", "password")
    print(f"CLONE workers={workers} force={force}", flush=True)
    subprocess.run(["zsh", str(CLONE_SCRIPT)], cwd=str(ROOT), env=env, check=True)


def count_worker_procs() -> int:
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", r"run_exhaustive_switch_grid\.py --worker-id"],
            text=True,
        )
        return len([ln for ln in out.splitlines() if ln.strip()])
    except subprocess.CalledProcessError:
        return 0


def spawn_worker(
    worker_id: int,
    workers: int,
    *,
    log_path: Path,
) -> subprocess.Popen:
    db_name = f"{DB_PREFIX}{worker_id}"
    env = os.environ.copy()
    env["DEV_DATABASE_URL"] = f"postgresql://cre:password@127.0.0.1:5432/{db_name}"
    env["PYTHONPATH"] = str(ROOT)
    env["FLASK_CONFIG"] = "development"
    env["NO_LOAD_GRAPH_DB"] = "1"
    env["CRE_LIBRARIAN_DEVICE"] = "cpu"
    env["CRE_LIBRARIAN_SHORTLIST_JUDGE"] = "0"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env.setdefault(
        "CRE_LIBRARIAN_CRE_SUMMARY_CACHE", str(ROOT / "tmp" / "oie_cre_summaries")
    )
    env.setdefault("PGPASSWORD", "password")
    cmd = [
        sys.executable,
        "-u",
        str(WORKER_SCRIPT),
        "--worker-id",
        str(worker_id),
        "--workers",
        str(workers),
        "--db-name",
        db_name,
        "--skip-artifacts",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", buffering=1)
    log_fh.write(f"\n===== WORKER {worker_id} start {_iso()} db={db_name} =====\n")
    log_fh.flush()
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    proc._log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def load_oie_env() -> None:
    oie_env = ROOT / "tmp" / "oie.env"
    if not oie_env.is_file():
        return
    for line in oie_env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--clone", action="store_true", help="Clone cre → cre_grid_w*")
    parser.add_argument(
        "--force-clone",
        action="store_true",
        help="Drop and recreate worker DBs",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Only rebuild artifacts / status and exit",
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Do not spawn workers; poll status until done / workers exit",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=30.0,
        help="Aggregator poll interval",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    os.chdir(ROOT)
    PARALLEL_DIR.mkdir(parents=True, exist_ok=True)
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    load_oie_env()

    if args.aggregate_only:
        done = refresh_artifacts()
        write_status_line(
            completed=done, total=512, last="aggregate_only", workers_alive=0
        )
        print(f"AGGREGATE_ONLY completed={done}", flush=True)
        return 0

    workers = max(1, int(args.workers))
    if args.clone or args.force_clone:
        clone_dbs(workers, force=bool(args.force_clone))

    procs: List[subprocess.Popen] = []
    pid_map: Dict[int, int] = {}

    if args.monitor_only:
        meta_path = PARALLEL_DIR / "launcher.json"
        if meta_path.is_file():
            try:
                prev = json.loads(meta_path.read_text())
                pid_map = {int(k): int(v) for k, v in (prev.get("pids") or {}).items()}
            except (json.JSONDecodeError, OSError, ValueError):
                pid_map = {}
        print(
            f"MONITOR_ONLY existing_workers={count_worker_procs()} known_pids={pid_map}",
            flush=True,
        )
        (PARALLEL_DIR / "monitor.json").write_text(
            json.dumps(
                {
                    "started_at": _iso(),
                    "mode": "monitor_only",
                    "workers": workers,
                    "pids": pid_map,
                    "dbs": [f"{DB_PREFIX}{i}" for i in range(workers)],
                    "pipeline_run_id": "orch-exp-baseline-20260921",
                },
                indent=2,
            )
            + "\n"
        )
        (PARALLEL_DIR / "monitor.pid").write_text(f"{os.getpid()}\n")
    else:
        for i in range(workers):
            db = f"{DB_PREFIX}{i}"
            chk = subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "cre",
                    "-d",
                    db,
                    "-tAc",
                    "SELECT count(*) FROM knowledge_queue "
                    "WHERE pipeline_run_id='orch-exp-baseline-20260921'",
                ],
                env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "password")},
                capture_output=True,
                text=True,
                check=False,
            )
            if chk.returncode != 0:
                print(
                    f"MISSING_DB {db}: run with --clone. stderr={chk.stderr}",
                    flush=True,
                )
                return 2
            print(f"DB_OK {db} kq={chk.stdout.strip()}", flush=True)

        for i in range(workers):
            log = PARALLEL_DIR / f"worker_{i}.log"
            proc = spawn_worker(i, workers, log_path=log)
            procs.append(proc)
            pid_map[i] = proc.pid
            print(
                f"SPAWNED worker={i} pid={proc.pid} db={DB_PREFIX}{i} log={log}",
                flush=True,
            )

        (PARALLEL_DIR / "launcher.json").write_text(
            json.dumps(
                {
                    "started_at": _iso(),
                    "workers": workers,
                    "pids": pid_map,
                    "dbs": [f"{DB_PREFIX}{i}" for i in range(workers)],
                    "pipeline_run_id": "orch-exp-baseline-20260921",
                },
                indent=2,
            )
            + "\n"
        )
        (PARALLEL_DIR / "launcher.pid").write_text(f"{os.getpid()}\n")

    stop = {"flag": False}

    def _handle_sig(_signum: int, _frame: Any) -> None:
        stop["flag"] = True
        print("AGGREGATOR_SIGNAL shutting down…", flush=True)
        for p in procs:
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                except OSError:
                    p.terminate()

    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)

    try:
        completed, total = count_completed()
    except Exception:  # noqa: BLE001
        completed, total = 0, 512
    alive_n = (
        count_worker_procs()
        if args.monitor_only
        else sum(1 for p in procs if p.poll() is None)
    )
    write_status_line(
        completed=completed,
        total=total,
        last="monitor_start" if args.monitor_only else "parallel_start",
        workers_alive=alive_n,
    )
    try:
        refresh_artifacts()
    except Exception:  # noqa: BLE001
        print("AGGREGATOR_REFRESH_FAIL initial", flush=True)

    while not stop["flag"]:
        try:
            alive_n = (
                count_worker_procs()
                if args.monitor_only
                else sum(1 for p in procs if p.poll() is None)
            )
            try:
                completed, total = count_completed()
            except Exception:  # noqa: BLE001
                print("COUNT_FAIL", flush=True)
            last = "parallel"
            if STATE_PATH.is_file():
                try:
                    last = str(json.loads(STATE_PATH.read_text()).get("last") or last)
                except (json.JSONDecodeError, OSError):
                    pass
            write_status_line(
                completed=completed,
                total=total,
                last=last,
                workers_alive=alive_n,
            )
            print(f"HEARTBEAT completed={completed}/{total} alive={alive_n}", flush=True)
            try:
                refresh_artifacts()
                print("REFRESH_OK", flush=True)
            except Exception:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                print("AGGREGATOR_REFRESH_FAIL", flush=True)

            if completed >= total:
                print(f"PARALLEL_DONE {completed}/{total}", flush=True)
                break
            if alive_n == 0:
                print("ALL_WORKERS_EXITED", flush=True)
                time.sleep(2)
                try:
                    refresh_artifacts()
                except Exception:  # noqa: BLE001
                    pass
                completed, total = count_completed()
                write_status_line(
                    completed=completed,
                    total=total,
                    last="workers_exited",
                    workers_alive=0,
                )
                break
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            print("MONITOR_LOOP_FAIL continuing", flush=True)
        time.sleep(max(5.0, float(args.poll_sec)))

    for p in procs:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except OSError:
                p.terminate()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except OSError:
                p.kill()
        fh = getattr(p, "_log_fh", None)
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass

    completed, total = count_completed()
    try:
        refresh_artifacts()
    except Exception:  # noqa: BLE001
        pass
    write_status_line(
        completed=completed,
        total=total,
        last="parallel_exit",
        workers_alive=count_worker_procs() if args.monitor_only else 0,
    )
    print(f"LAUNCHER_EXIT completed={completed}/{total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
