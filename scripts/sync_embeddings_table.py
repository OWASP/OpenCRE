#!/usr/bin/env python3
"""
Copy only the ``embeddings`` table between databases.

Typical flow (embeddings live in local SQLite):

  1) Push into local Postgres (same ``cre`` / ``node`` ids as in the sqlite file):

       python scripts/sync_embeddings_table.py \\
         --from-sqlite /path/to/standards_cache.sqlite \\
         --to-postgres postgresql://cre:password@127.0.0.1:5432/cre

  2) Push from that local Postgres into a remote Postgres (schema must match):

       python scripts/sync_embeddings_table.py \\
         --from-postgres postgresql://cre:password@127.0.0.1:5432/cre \\
         --to-postgres 'postgresql://user:pass@remote.example/db?sslmode=require'

Foreign keys on ``embeddings`` reference ``cre`` and ``node``; every ``cre_id`` /
``node_id`` in the source rows must already exist on the target or inserts will fail.

Requires: psycopg2 (see requirements.txt). SQLite uses the stdlib ``sqlite3`` module.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import urllib.parse
from typing import Any, List, Sequence, Tuple

import psycopg2
from psycopg2 import extras


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value == "":
        return None
    return value


def _normalize_embedding_row(row: Tuple[Any, ...]) -> Tuple[Any, ...]:
    # SQLite snapshots often store "missing" FK fields as empty strings.
    # Postgres FK checks treat empty string as a real value (not NULL),
    # so convert blanks to NULL for cre_id/node_id before insert.
    embeddings, doc_type, cre_id, node_id, embeddings_content, embeddings_url = row
    return (
        embeddings,
        doc_type,
        _blank_to_none(cre_id),
        _blank_to_none(node_id),
        _blank_to_none(embeddings_content),
        _blank_to_none(embeddings_url),
    )


def _normalize_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _pg_host_is_loopback(url: str) -> bool:
    p = urllib.parse.urlparse(_normalize_pg_url(url))
    h = (p.hostname or "").lower()
    return h in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or h == ""


def _fetch_sqlite_embeddings(path: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT embeddings, doc_type, cre_id, node_id, embeddings_content, embeddings_url "
        "FROM embeddings"
    )
    rows = [_normalize_embedding_row(tuple(r)) for r in cur.fetchall()]
    conn.close()
    cols = [
        "embeddings",
        "doc_type",
        "cre_id",
        "node_id",
        "embeddings_content",
        "embeddings_url",
    ]
    return cols, rows


def _fetch_postgres_embeddings(pg_url: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    cols = [
        "embeddings",
        "doc_type",
        "cre_id",
        "node_id",
        "embeddings_content",
        "embeddings_url",
    ]
    quoted = ", ".join(f'"{c}"' for c in cols)
    conn = psycopg2.connect(_normalize_pg_url(pg_url))
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {quoted} FROM public.embeddings")
        rows = [_normalize_embedding_row(tuple(r)) for r in cur.fetchall()]
        cur.close()
        return cols, rows
    finally:
        conn.close()


def _replace_postgres_embeddings(pg_url: str, rows: Sequence[Tuple[Any, ...]]) -> None:
    url = _normalize_pg_url(pg_url)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM public.embeddings")
        if rows:
            extras.execute_batch(
                cur,
                """
                INSERT INTO public.embeddings (
                    embeddings, doc_type, cre_id, node_id, embeddings_content, embeddings_url
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                list(rows),
                page_size=500,
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from-sqlite",
        metavar="PATH",
        help="Source SQLite database file (reads public.embeddings-style table named embeddings)",
    )
    src.add_argument(
        "--from-postgres",
        metavar="URL",
        help="Source Postgres URL (SQLAlchemy or libpq form)",
    )
    p.add_argument(
        "--to-postgres",
        required=True,
        metavar="URL",
        help="Destination Postgres URL",
    )
    p.add_argument(
        "--require-local-destination",
        action="store_true",
        help="Refuse --to-postgres unless the host is loopback (safety guard)",
    )
    p.add_argument(
        "--allow-nonloopback-destination",
        action="store_true",
        help="Acknowledge remote --to-postgres (required when not using --require-local-destination and URL is not loopback)",
    )
    args = p.parse_args()

    dest = args.to_postgres
    if args.require_local_destination and not _pg_host_is_loopback(dest):
        print(
            "error: --require-local-destination set but --to-postgres is not loopback",
            file=sys.stderr,
        )
        return 2
    if not _pg_host_is_loopback(dest) and not args.allow_nonloopback_destination:
        print(
            "error: --to-postgres looks non-local; pass "
            "--allow-nonloopback-destination to confirm, or use "
            "--require-local-destination when writing only to localhost",
            file=sys.stderr,
        )
        return 2

    if args.from_sqlite:
        _, rows = _fetch_sqlite_embeddings(args.from_sqlite)
        print(f"read {len(rows)} embedding row(s) from sqlite {args.from_sqlite!r}")
    else:
        _, rows = _fetch_postgres_embeddings(args.from_postgres)
        print(f"read {len(rows)} embedding row(s) from postgres")

    _replace_postgres_embeddings(dest, rows)
    print(f"wrote {len(rows)} embedding row(s) to {dest!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
