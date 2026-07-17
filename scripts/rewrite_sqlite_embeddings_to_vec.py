#!/usr/bin/env python3
"""Rewrite a SQLite embeddings cache from legacy CSV to ``embedding_vec`` Text.

After Alembic ``c7d8e9f0a1b2``, OpenCRE stores vectors only in ``embedding_vec``
(Postgres: real ``vector(N)``; SQLite / CI: Text literals ``[1.0,2.0,...]``).
Old ``standards_cache.sqlite`` files still have a CSV ``embeddings`` column —
the ORM will refuse them. This script converts in place:

  * ADD ``embedding_vec`` TEXT (if missing)
  * copy CSV → ``[…]`` literal without double-bracketing
  * DROP ``embeddings`` via table recreate (rerun-safe)

Usage::

  python scripts/rewrite_sqlite_embeddings_to_vec.py --db standards_cache.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
import sys


def _csv_to_literal(csv: str) -> str:
    s = (csv or "").strip()
    if s.startswith("[") and s.endswith("]"):
        return s
    return f"[{s}]"


def rewrite(path: str) -> int:
    conn = sqlite3.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
        if not cols:
            print(f"error: no embeddings table in {path!r}", file=sys.stderr)
            return 2
        if "embedding_vec" in cols and "embeddings" not in cols:
            print(f"{path}: already embedding_vec-only; nothing to do")
            return 0
        if "embeddings" not in cols:
            print(
                f"error: {path} has embedding_vec but no CSV embeddings column "
                "and is incomplete; refusing to rewrite",
                file=sys.stderr,
            )
            return 2
        if "embedding_vec" not in cols:
            conn.execute("ALTER TABLE embeddings ADD COLUMN embedding_vec TEXT")

        # Copy only rows still missing a vector; never wrap an already-bracketed
        # CSV twice (some caches may already store ``[1,2]`` in the CSV column).
        rows = conn.execute(
            """
            SELECT rowid, embeddings, embedding_vec
            FROM embeddings
            WHERE embeddings IS NOT NULL
              AND trim(embeddings) <> ''
              AND (embedding_vec IS NULL OR trim(embedding_vec) = '')
            """
        ).fetchall()
        for rowid, csv, _existing in rows:
            conn.execute(
                "UPDATE embeddings SET embedding_vec = ? WHERE rowid = ?",
                (_csv_to_literal(str(csv)), rowid),
            )

        nulls = conn.execute(
            "SELECT COUNT(*) FROM embeddings "
            "WHERE embedding_vec IS NULL OR trim(embedding_vec) = ''"
        ).fetchone()[0]
        if nulls:
            print(
                f"error: {nulls} row(s) still lack embedding_vec after copy; "
                "refusing to drop CSV column",
                file=sys.stderr,
            )
            conn.rollback()
            return 3
        conn.commit()

        # SQLite lacks reliable DROP COLUMN on older builds; recreate table.
        # Drop any leftover embeddings_new from a prior interrupted run.
        conn.execute("DROP TABLE IF EXISTS embeddings_new")
        src_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(embeddings)").fetchall()
        }
        select_id = "id" if "id" in src_cols else "NULL"
        select_model = (
            "embedding_model_id" if "embedding_model_id" in src_cols else "NULL"
        )
        select_dim = "embedding_dim" if "embedding_dim" in src_cols else "NULL"
        select_url = "embeddings_url" if "embeddings_url" in src_cols else "NULL"
        select_content = (
            "embeddings_content" if "embeddings_content" in src_cols else "NULL"
        )
        conn.execute(
            """
            CREATE TABLE embeddings_new (
                id TEXT PRIMARY KEY,
                doc_type TEXT NOT NULL,
                cre_id TEXT,
                node_id TEXT,
                embeddings_url TEXT,
                embeddings_content TEXT,
                embedding_model_id TEXT,
                embedding_dim INTEGER,
                embedding_vec TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO embeddings_new (
                id, doc_type, cre_id, node_id, embeddings_url,
                embeddings_content, embedding_model_id, embedding_dim, embedding_vec
            )
            SELECT
                {select_id}, doc_type, cre_id, node_id, {select_url},
                {select_content}, {select_model}, {select_dim}, embedding_vec
            FROM embeddings
            """
        )
        conn.execute("DROP TABLE embeddings")
        conn.execute("ALTER TABLE embeddings_new RENAME TO embeddings")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        print(f"{path}: rewrote {n} row(s) to embedding_vec-only")
        return 0
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, help="Path to SQLite database file")
    args = p.parse_args()
    return rewrite(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
