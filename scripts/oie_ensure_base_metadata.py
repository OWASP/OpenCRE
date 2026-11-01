#!/usr/bin/env python3
"""Ensure deterministic OIE base metadata on Nodes then CREs (fill-if-missing).

Runs ``oie_tag_standard_sections`` then ``oie_tag_cre_families``. Does not call
the LLM enricher. Used by ``make oie-tag-base`` and ``scripts/setup_oie.sh``.

Usage:
  PYTHONPATH=. python scripts/oie_ensure_base_metadata.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre_prodclone

  PYTHONPATH=. python scripts/oie_ensure_base_metadata.py --dry-run
  PYTHONPATH=. python scripts/oie_ensure_base_metadata.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPTS_DIR)


def _run(script: str, cache_file: str, *, dry_run: bool, force: bool) -> Dict[str, Any]:
    cmd: List[str] = [
        sys.executable,
        os.path.join(_SCRIPTS_DIR, script),
        "--cache-file",
        cache_file,
    ]
    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", _ROOT)
    if env.get("PYTHONPATH") and _ROOT not in env["PYTHONPATH"].split(os.pathsep):
        env["PYTHONPATH"] = _ROOT + os.pathsep + env["PYTHONPATH"]
    elif not env.get("PYTHONPATH"):
        env["PYTHONPATH"] = _ROOT
    proc = subprocess.run(
        cmd,
        cwd=_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "")
        raise SystemExit(proc.returncode)
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out) if out else {}
    except json.JSONDecodeError:
        # Scripts print JSON only; if mixed, take last {...} block.
        start = out.rfind("{")
        if start >= 0:
            return json.loads(out[start:])
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get(
            "CACHE_FILE",
            os.environ.get(
                "DEV_DATABASE_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
            ),
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    nodes = _run(
        "oie_tag_standard_sections.py",
        args.cache_file,
        dry_run=args.dry_run,
        force=args.force,
    )
    cres = _run(
        "oie_tag_cre_families.py",
        args.cache_file,
        dry_run=args.dry_run,
        force=args.force,
    )
    report = {
        "cache_file": args.cache_file,
        "dry_run": args.dry_run,
        "force": args.force,
        "nodes": nodes,
        "cres": cres,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
