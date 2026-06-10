#!/usr/bin/env python3
"""Copy material ``gap_analysis_results`` rows between databases (upsert only)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.parse
from typing import Iterable, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2 import extras


def _normalize_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _pg_host_is_loopback(url: str) -> bool:
    p = urllib.parse.urlparse(_normalize_pg_url(url))
    h = (p.hostname or "").lower()
    return h in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or h == ""


def _redact_pg_url(url: str) -> str:
    p = urllib.parse.urlparse(_normalize_pg_url(url))
    host = p.hostname or "unknown"
    port = f":{p.port}" if p.port else ""
    db = (p.path or "").lstrip("/") or "postgres"
    return f"postgresql://***@{host}{port}/{db}"


def _is_primary_cache_key(cache_key: str) -> bool:
    marker = " >> "
    idx = cache_key.find(marker)
    if idx < 0:
        return False
    return "->" not in cache_key[idx + len(marker) :]


def _payload_is_material(ga_object: Optional[str]) -> bool:
    if not ga_object or not isinstance(ga_object, str):
        return False
    try:
        parsed = json.loads(ga_object)
    except json.JSONDecodeError:
        return False
    res = parsed.get("result")
    if res is None:
        return False
    if isinstance(res, (dict, list)):
        return len(res) > 0
    return bool(res)


def _fetch_sqlite_rows(
    path: str, material_only: bool
) -> List[Tuple[str, Optional[str]]]:
    conn = sqlite3.connect(path)
    cur = conn.execute("SELECT cache_key, ga_object FROM gap_analysis_results")
    rows: List[Tuple[str, Optional[str]]] = []
    for k, v in cur.fetchall():
        payload = None if v is None else str(v)
        if material_only and not _payload_is_material(payload):
            continue
        rows.append((str(k), payload))
    conn.close()
    return rows


def _fetch_postgres_rows(
    pg_url: str, material_only: bool
) -> List[Tuple[str, Optional[str]]]:
    conn = psycopg2.connect(_normalize_pg_url(pg_url))
    try:
        cur = conn.cursor()
        cur.execute("SELECT cache_key, ga_object FROM public.gap_analysis_results")
        rows: List[Tuple[str, Optional[str]]] = []
        for cache_key, ga_object in cur.fetchall():
            payload = None if ga_object is None else str(ga_object)
            if material_only and not _payload_is_material(payload):
                continue
            rows.append((str(cache_key), payload))
        cur.close()
        return rows
    finally:
        conn.close()


def _existing_primary_payloads(
    cur: psycopg2.extensions.cursor, cache_keys: Sequence[str]
) -> dict[str, Optional[str]]:
    primary_keys = [k for k in cache_keys if _is_primary_cache_key(k)]
    if not primary_keys:
        return {}
    cur.execute(
        "SELECT cache_key, ga_object FROM public.gap_analysis_results "
        "WHERE cache_key = ANY(%s)",
        (list(primary_keys),),
    )
    return {str(k): v for k, v in cur.fetchall()}


def _may_overwrite_primary(
    cache_key: str,
    new_payload: Optional[str],
    existing_payload: Optional[str],
) -> bool:
    if not _is_primary_cache_key(cache_key):
        return True
    if _payload_is_material(new_payload):
        return True
    if existing_payload is None:
        return False
    return not _payload_is_material(existing_payload)


def _merge_postgres_rows(
    pg_url: str, rows: Sequence[Tuple[str, Optional[str]]]
) -> None:
    """Update existing rows and insert missing keys (works without a unique index)."""
    conn = psycopg2.connect(_normalize_pg_url(pg_url))
    conn.autocommit = False
    batch_size = 500
    try:
        cur = conn.cursor()
        for i in range(0, len(rows), batch_size):
            batch = list(rows[i : i + batch_size])
            existing_by_key = _existing_primary_payloads(cur, [k for k, _ in batch])
            batch = [
                (k, v)
                for k, v in batch
                if _may_overwrite_primary(k, v, existing_by_key.get(k))
            ]
            if not batch:
                continue
            cur.execute(
                """
                CREATE TEMP TABLE ga_sync_stage (
                    cache_key text PRIMARY KEY,
                    ga_object text
                ) ON COMMIT DROP
                """
            )
            extras.execute_batch(
                cur,
                "INSERT INTO ga_sync_stage (cache_key, ga_object) VALUES (%s, %s)",
                batch,
                page_size=200,
            )
            cur.execute(
                """
                UPDATE public.gap_analysis_results AS g
                SET ga_object = s.ga_object
                FROM ga_sync_stage AS s
                WHERE g.cache_key = s.cache_key
                """
            )
            cur.execute(
                """
                INSERT INTO public.gap_analysis_results (cache_key, ga_object)
                SELECT s.cache_key, s.ga_object
                FROM ga_sync_stage AS s
                LEFT JOIN public.gap_analysis_results AS g
                  ON g.cache_key = s.cache_key
                WHERE g.cache_key IS NULL
                """
            )
            conn.commit()
            print(
                f"merged batch {i // batch_size + 1}: {len(batch)} row(s)",
                flush=True,
            )
        cur.close()
    finally:
        conn.close()


def _fetch_rows(
    from_sqlite: Optional[str],
    from_postgres: Optional[str],
    material_only: bool,
) -> List[Tuple[str, Optional[str]]]:
    if from_sqlite:
        return _fetch_sqlite_rows(from_sqlite, material_only)
    if from_postgres:
        return _fetch_postgres_rows(from_postgres, material_only)
    raise ValueError("one of --from-sqlite or --from-postgres is required")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-sqlite", metavar="PATH")
    src.add_argument("--from-postgres", metavar="URL")
    p.add_argument("--to-postgres", required=True, metavar="URL")
    p.add_argument(
        "--material-only",
        action="store_true",
        default=True,
        help="Sync only rows with non-empty result payloads (default: true)",
    )
    p.add_argument(
        "--include-non-material",
        action="store_true",
        help="Also sync empty/placeholder rows (overrides --material-only)",
    )
    p.add_argument("--require-local-destination", action="store_true")
    p.add_argument("--allow-nonloopback-destination", action="store_true")
    args = p.parse_args()

    material_only = not args.include_non_material

    if args.require_local_destination and not _pg_host_is_loopback(args.to_postgres):
        print("error: destination is not loopback", file=sys.stderr)
        return 2
    if (
        not _pg_host_is_loopback(args.to_postgres)
        and not args.allow_nonloopback_destination
    ):
        print(
            "error: remote destination requires --allow-nonloopback-destination",
            file=sys.stderr,
        )
        return 2

    rows = _fetch_rows(args.from_sqlite, args.from_postgres, material_only)
    if args.from_postgres:
        source_label = _redact_pg_url(args.from_postgres)
    else:
        source_label = args.from_sqlite or "unknown"
    print(
        f"read {len(rows)} row(s) from {source_label!r} (material_only={material_only})"
    )
    _merge_postgres_rows(args.to_postgres, rows)
    print(f"merged {len(rows)} row(s) to {_redact_pg_url(args.to_postgres)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
