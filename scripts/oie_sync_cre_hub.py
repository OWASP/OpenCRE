#!/usr/bin/env python3
"""Sync the Module C CRE hub (``cre`` + CRE ``embeddings``) into local Postgres.

Used by ``scripts/setup_oie.sh``. Does **not** touch standards/nodes beyond what
CRE embedding FKs require: only ``cre`` rows referenced by CRE embeddings, plus
those embedding rows (vectors + ``embeddings_content`` for C.2).

Sources
  --from-sqlite PATH
  --from-postgres URL   (e.g. Heroku DATABASE_URL; read-only)

Destination is always local Postgres (``--to-postgres``), default
``postgresql://cre:password@127.0.0.1:5432/cre``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.parse
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2 import extras


def _normalize_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _as_vec_literal(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "[]":
        return None
    if s.startswith("[") and s.endswith("]"):
        return s if s[1:-1].strip() else None
    if not any(part.strip() for part in s.split(",")):
        return None
    return f"[{s}]"


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value == "":
        return None
    return value


def _fetch_sqlite(
    path: str,
) -> Tuple[List[Tuple[Any, ...]], List[Tuple[Any, ...]]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)")}
    if "embedding_vec" in cols:
        vec_col = "embedding_vec"
    elif "embeddings" in cols:
        vec_col = "embeddings"
    else:
        conn.close()
        raise SystemExit("sqlite embeddings has neither embedding_vec nor embeddings")

    emb_rows: List[Tuple[Any, ...]] = []
    cre_ids: List[str] = []
    has_model = "embedding_model_id" in cols
    has_dim = "embedding_dim" in cols
    select = (
        f"SELECT {vec_col}, cre_id, embeddings_content, embeddings_url"
        + (", embedding_model_id" if has_model else ", NULL")
        + (", embedding_dim" if has_dim else ", NULL")
        + " FROM embeddings WHERE doc_type = 'CRE' AND cre_id IS NOT NULL "
        "AND cre_id != ''"
    )
    for r in conn.execute(select):
        lit = _as_vec_literal(r[0])
        if lit is None:
            continue
        cre_id = str(r[1])
        cre_ids.append(cre_id)
        emb_rows.append(
            (
                lit,
                "CRE",
                cre_id,
                None,
                _blank_to_none(r[2]),
                _blank_to_none(r[3]),
                _blank_to_none(r[4]),
                r[5],
            )
        )

    if not cre_ids:
        conn.close()
        return [], []

    placeholders = ",".join("?" for _ in cre_ids)
    # Unique ids while preserving order for stable upserts.
    seen = set()
    ordered_ids: List[str] = []
    for i in cre_ids:
        if i not in seen:
            seen.add(i)
            ordered_ids.append(i)
    placeholders = ",".join("?" for _ in ordered_ids)
    cre_rows = [
        (
            r["id"],
            r["external_id"] or "",
            r["description"] or "",
            r["name"],
            r["tags"] or "",
        )
        for r in conn.execute(
            f"SELECT id, external_id, description, name, tags FROM cre "
            f"WHERE id IN ({placeholders})",
            ordered_ids,
        )
    ]
    conn.close()
    return cre_rows, emb_rows


def _fetch_postgres(
    pg_url: str,
) -> Tuple[List[Tuple[Any, ...]], List[Tuple[Any, ...]]]:
    url = _normalize_pg_url(pg_url)
    # Heroku URLs often need sslmode=require
    if "amazonaws.com" in url or "heroku" in url:
        if "sslmode=" not in url:
            url = url + ("&" if "?" in url else "?") + "sslmode=require"

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding_vec::text, cre_id, embeddings_content, embeddings_url, "
                "embedding_model_id, embedding_dim "
                "FROM embeddings WHERE doc_type = 'CRE' AND cre_id IS NOT NULL"
            )
            emb_rows: List[Tuple[Any, ...]] = []
            cre_ids: List[str] = []
            for vec, cre_id, content, eurl, model_id, dim in cur.fetchall():
                lit = _as_vec_literal(vec)
                if lit is None or not cre_id:
                    continue
                cre_ids.append(str(cre_id))
                emb_rows.append(
                    (
                        lit,
                        "CRE",
                        str(cre_id),
                        None,
                        _blank_to_none(content),
                        _blank_to_none(eurl),
                        _blank_to_none(model_id),
                        dim,
                    )
                )
            if not cre_ids:
                return [], []
            seen = set()
            ordered_ids: List[str] = []
            for i in cre_ids:
                if i not in seen:
                    seen.add(i)
                    ordered_ids.append(i)
            cur.execute(
                "SELECT id, COALESCE(external_id,''), COALESCE(description,''), "
                "name, COALESCE(tags,'') FROM cre WHERE id = ANY(%s)",
                (ordered_ids,),
            )
            cre_rows = [tuple(r) for r in cur.fetchall()]
    return cre_rows, emb_rows


def _upsert_cre(conn: Any, rows: Sequence[Tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO cre (id, external_id, description, name, tags)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
          external_id = EXCLUDED.external_id,
          description = EXCLUDED.description,
          name = EXCLUDED.name,
          tags = EXCLUDED.tags
    """
    with conn.cursor() as cur:
        extras.execute_values(cur, sql, rows, page_size=500)
    return len(rows)


def _replace_cre_embeddings(conn: Any, rows: Sequence[Tuple[Any, ...]]) -> int:
    """Replace CRE embedding rows (keeps non-CRE embeddings untouched)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM embeddings WHERE doc_type = 'CRE'")
        if not rows:
            return 0
        sql = """
            INSERT INTO embeddings (
              embedding_vec, doc_type, cre_id, node_id,
              embeddings_content, embeddings_url,
              embedding_model_id, embedding_dim
            ) VALUES %s
        """
        # Cast vector literal in template
        extras.execute_values(
            cur,
            sql,
            rows,
            template="(%s::vector, %s, %s, %s, %s, %s, %s, %s)",
            page_size=200,
        )
    return len(rows)


def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-sqlite", metavar="PATH")
    src.add_argument("--from-postgres", metavar="URL")
    p.add_argument(
        "--to-postgres",
        default="postgresql://cre:password@127.0.0.1:5432/cre",
        metavar="URL",
    )
    p.add_argument(
        "--require-local-destination",
        action="store_true",
        default=True,
        help="refuse non-loopback --to-postgres (default on)",
    )
    p.add_argument(
        "--allow-remote-destination",
        action="store_true",
        help="allow non-loopback --to-postgres",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    dest = _normalize_pg_url(args.to_postgres)
    host = (urllib.parse.urlparse(dest).hostname or "").lower()
    local = host in ("127.0.0.1", "localhost", "::1", "") or host == "0.0.0.0"
    if (
        args.require_local_destination
        and not args.allow_remote_destination
        and not local
    ):
        print(
            "error: --to-postgres is not loopback; pass --allow-remote-destination",
            file=sys.stderr,
        )
        return 2

    if args.from_sqlite:
        cre_rows, emb_rows = _fetch_sqlite(args.from_sqlite)
        source = f"sqlite:{args.from_sqlite}"
    else:
        cre_rows, emb_rows = _fetch_postgres(args.from_postgres)
        source = "postgres:upstream"

    print(
        f"source={source} cre_rows={len(cre_rows)} cre_embeddings={len(emb_rows)}",
        flush=True,
    )
    if not emb_rows:
        print("error: no CRE embeddings in source", file=sys.stderr)
        return 1

    with psycopg2.connect(dest) as conn:
        n_cre = _upsert_cre(conn, cre_rows)
        n_emb = _replace_cre_embeddings(conn, emb_rows)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM cre")
            cre_total = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM embeddings WHERE doc_type = 'CRE' "
                "AND embedding_vec IS NOT NULL"
            )
            emb_total = cur.fetchone()[0]

    report = {
        "upserted_cre": n_cre,
        "replaced_cre_embeddings": n_emb,
        "dest_cre_total": cre_total,
        "dest_cre_embeddings_with_vec": emb_total,
        "to": dest,
    }
    print(json.dumps(report, indent=2))
    return 0 if emb_total else 1


if __name__ == "__main__":
    sys.exit(main())
