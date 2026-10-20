#!/usr/bin/env python3
"""Run adversarial asker in fresh-process batches (avoids MCP stdio stalls)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    start = int(os.environ.get("OWASP_ADV_START_TURN") or "1")
    end = int(os.environ.get("OWASP_ADV_MAX_TURNS") or "2000")
    batch = int(os.environ.get("OWASP_ADV_BATCH") or "50")
    timeout = int(os.environ.get("OWASP_ADV_BATCH_TIMEOUT") or "480")
    out = os.environ.get(
        "OWASP_ADV_OUT", str(_REPO / "tmp" / "owasp_agent_adversarial_failures.jsonl")
    )
    log_path = Path(
        os.environ.get(
            "OWASP_ADV_BATCH_LOG",
            str(_REPO / "tmp" / "owasp_agent_adversarial_2000b.log"),
        )
    )
    py = str(_REPO / "venv" / "bin" / "python")
    if not Path(py).is_file():
        py = sys.executable
    script = str(_REPO / "scripts" / "owasp_agent_adversarial_asker.py")

    env_base = {
        **os.environ,
        "OWASP_PROBE_COMPLETION_MODE": os.environ.get(
            "OWASP_PROBE_COMPLETION_MODE", "mcp_ask"
        ),
        "OWASP_ADV_MCP_TRANSPORT": os.environ.get(
            "OWASP_ADV_MCP_TRANSPORT", "staging_ssh"
        ),
        "OWASP_ADV_ASK_TIMEOUT": os.environ.get("OWASP_ADV_ASK_TIMEOUT", "35"),
        "OWASP_ADV_APPEND": "1",
        "OWASP_ADV_OUT": out,
        "OWASP_ADV_SEED": os.environ.get("OWASP_ADV_SEED", "14"),
        "OWASP_AGENT_ENABLED": "1",
        "PYTHONUNBUFFERED": "1",
    }

    with log_path.open("a") as log:
        t = start
        while t <= end:
            batch_end = min(t + batch - 1, end)
            msg = f"BATCH {t}-{batch_end} {time.strftime('%H:%M:%S', time.gmtime())}\n"
            log.write(msg)
            log.flush()
            print(msg, end="", flush=True)
            env = {
                **env_base,
                "OWASP_ADV_START_TURN": str(t),
                "OWASP_ADV_MAX_TURNS": str(batch_end),
            }
            try:
                proc = subprocess.run(
                    [py, "-u", script],
                    cwd=str(_REPO),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                ec = proc.returncode
            except subprocess.TimeoutExpired:
                log.write(f"WATCHDOG_KILL batch {t}-{batch_end}\n")
                log.flush()
                ec = 124
            done = (
                f"BATCH_DONE {t}-{batch_end} exit={ec} "
                f"{time.strftime('%H:%M:%S', time.gmtime())}\n"
            )
            log.write(done)
            log.flush()
            print(done, end="", flush=True)
            t = batch_end + 1
        log.write(f"ALL_BATCHES_DONE {time.strftime('%H:%M:%S', time.gmtime())}\n")
        log.flush()
    print("ALL_BATCHES_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
