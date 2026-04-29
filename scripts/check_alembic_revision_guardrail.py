#!/usr/bin/env python3
"""
Deploy guardrail: fail fast when the target DB's alembic revision(s) do not
exist in this app's migration tree.

Intended usage:
  python scripts/check_alembic_revision_guardrail.py

Environment:
  - DATABASE_URL or SQLALCHEMY_DATABASE_URI must be set.
"""

from __future__ import annotations

import glob
import os
import re
import sys
from typing import Set

import sqlalchemy as sa


def _normalized_db_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        url = (os.environ.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL/SQLALCHEMY_DATABASE_URI is not set")
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _known_revisions(repo_root: str) -> Set[str]:
    revs: Set[str] = set()
    pattern = os.path.join(repo_root, "migrations", "versions", "*.py")
    for path in glob.glob(pattern):
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", txt)
        if m:
            revs.add(m.group(1))
    return revs


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    known = _known_revisions(repo_root)
    if not known:
        raise RuntimeError("No migration revisions found in migrations/versions")

    url = _normalized_db_url()
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).fetchall()
    db_revs = [str(r[0]) for r in rows]
    if not db_revs:
        raise RuntimeError("alembic_version table is empty")

    unknown = [r for r in db_revs if r not in known]
    if unknown:
        print(
            "ALEMBIC_GUARDRAIL_FAIL: DB revision(s) not present in app migration tree:",
            ", ".join(unknown),
        )
        print("Known heads/revisions count:", len(known))
        return 2

    print(
        "ALEMBIC_GUARDRAIL_OK: all DB revision(s) exist in app migration tree:",
        ", ".join(db_revs),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ALEMBIC_GUARDRAIL_ERROR: {e}")
        raise
