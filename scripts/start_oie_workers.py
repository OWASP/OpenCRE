#!/usr/bin/env python3
"""Double-fork N RQ workers on queue ``oie`` (survives make/shell exit)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def spawn_one(index: int, env: dict) -> None:
    log = REPO / f"worker-oie-{index}.log"
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    os.chdir(REPO)
    py = str(REPO / "venv" / "bin" / "python")
    os.execve(py, [py, "cre.py", "--start_worker"], env)


def main() -> int:
    n = int(os.environ.get("OIE_WORKER_COUNT", "10"))
    sys.path.insert(0, str(REPO))
    from application.utils.librarian.config_loader import apply_promoted_defaults

    apply_promoted_defaults()
    env = os.environ.copy()
    env["CRE_WORKER_QUEUES"] = "oie"
    env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    env.setdefault(
        "CRE_LIBRARIAN_CRE_SUMMARY_CACHE",
        str(REPO / "tmp" / "oie_cre_summaries"),
    )
    env["FLASK_APP"] = str(REPO / "cre.py")
    env.setdefault("PYTHONPATH", str(REPO))
    for i in range(1, n + 1):
        spawn_one(i, env)
        time.sleep(0.05)
        print(f"started oie worker {i} -> worker-oie-{i}.log", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
