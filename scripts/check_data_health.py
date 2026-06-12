#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

from application.utils import data_health


def _fetch_rows(conn: Any, query: str) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def load_snapshot(db_url: str) -> data_health.Snapshot:
    conn = psycopg2.connect(db_url)
    try:
        rows = {
            "cre": _fetch_rows(
                conn, "SELECT id, external_id, name, description, tags FROM cre"
            ),
            "node": _fetch_rows(
                conn,
                "SELECT id, name, section, subsection, section_id, version, "
                "description, tags, ntype, link FROM node",
            ),
            "cre_links": _fetch_rows(conn, 'SELECT type, "group", cre FROM cre_links'),
            "cre_node_links": _fetch_rows(
                conn, "SELECT type, cre, node FROM cre_node_links"
            ),
        }
        return data_health.build_canonical_snapshot(rows)
    finally:
        conn.close()


def _counts(snapshot: data_health.Snapshot) -> Dict[str, int]:
    return {table: len(rows) for table, rows in snapshot.items()}


def _to_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare OpenCRE data equivalency between two PostgreSQL databases."
    )
    parser.add_argument("--db1-url", required=True, help="Known-good database URL.")
    parser.add_argument("--db2-url", required=True, help="Current database URL.")
    parser.add_argument("--db1-label", default="db1", help="Label for database 1.")
    parser.add_argument("--db2-label", default="db2", help="Label for database 2.")
    args = parser.parse_args()

    snapshot_1 = load_snapshot(args.db1_url)
    snapshot_2 = load_snapshot(args.db2_url)

    digest_1 = data_health.snapshot_digest(snapshot_1)
    digest_2 = data_health.snapshot_digest(snapshot_2)

    print(f"{args.db1_label} counts: {_to_json(_counts(snapshot_1))}")
    print(f"{args.db2_label} counts: {_to_json(_counts(snapshot_2))}")
    print(f"{args.db1_label} digest: {digest_1}")
    print(f"{args.db2_label} digest: {digest_2}")

    if digest_1 == digest_2:
        print("Data health check passed: datasets are equivalent.")
        return 0

    diff_1_to_2 = data_health.snapshot_diff(snapshot_1, snapshot_2)
    diff_2_to_1 = data_health.snapshot_diff(snapshot_2, snapshot_1)
    print("Data health check failed: dataset mismatch detected.")
    print(f"{args.db1_label} -> {args.db2_label} diff:")
    print(_to_json(diff_1_to_2))
    print(f"{args.db2_label} -> {args.db1_label} diff:")
    print(_to_json(diff_2_to_1))
    return 1


if __name__ == "__main__":
    sys.exit(main())
