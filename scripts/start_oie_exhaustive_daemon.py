#!/usr/bin/env python3
"""Double-fork the exhaustive incremental runner so it survives Cursor/shell exit."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "tmp" / "oie_exhaustive"
LOG_DIR = REPO / "logs"


def main() -> int:
    run_id = (
        os.environ.get("OIE_EXHAUSTIVE_RUN_ID")
        or (OUT / "run_id.txt").read_text(encoding="utf-8").strip()
        if (OUT / "run_id.txt").is_file()
        else ""
    ).strip()
    if not run_id:
        print(
            "missing run_id (set OIE_EXHAUSTIVE_RUN_ID or tmp/oie_exhaustive/run_id.txt)"
        )
        return 2

    cache = (
        os.environ.get("DEV_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql://cre:password@127.0.0.1:5432/cre"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"oie_exhaustive_{run_id}.log"
    pid_path = OUT / "runner.pid"

    # Kill prior coordinator if still alive.
    if pid_path.is_file():
        try:
            old = int(pid_path.read_text().strip())
            os.kill(old, 0)
            os.kill(old, 15)
            time.sleep(1)
        except (ValueError, OSError, ProcessLookupError):
            pass

    py = str(REPO / "venv" / "bin" / "python")
    script = str(REPO / "scripts" / "run_oie_exhaustive_incremental.py")
    argv = [
        py,
        "-u",
        script,
        "--run_id",
        run_id,
        "--cache_file",
        cache,
        "--out-dir",
        str(OUT),
    ]

    if os.fork() > 0:
        time.sleep(0.3)
        print(f"daemonizing exhaustive runner run_id={run_id} log={log_path}")
        if pid_path.is_file():
            print(f"pid={pid_path.read_text().strip()}")
        return 0

    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    os.chdir(REPO)
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    # stdin -> /dev/null
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO))
    env.setdefault("FLASK_CONFIG", "development")
    env.setdefault("NO_LOAD_GRAPH_DB", "1")
    env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    env["DEV_DATABASE_URL"] = cache

    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    os.execve(py, argv, env)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
