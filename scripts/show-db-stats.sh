#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${1:-$ROOT_DIR/standards_cache.sqlite}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

echo "Database: $DB_PATH"
du -h "$DB_PATH"

"$ROOT_DIR/venv/bin/python" - "$DB_PATH" <<'PY'
import os
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print(f"size_bytes {os.path.getsize(db_path)}")

tables = [
    "node",
    "cre",
    "cre_links",
    "cre_node_links",
    "embeddings",
]

for table in tables:
    try:
        count = cur.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"{table}_count {count}")
    except sqlite3.Error as exc:
        print(f"{table}_count unavailable ({exc})")

try:
    standards = cur.execute(
        """
        select name, count(*)
        from node
        where name is not null
        group by name
        order by count(*) desc, name asc
        limit 15
        """
    ).fetchall()
    print("top_standards")
    for name, count in standards:
        print(f"{name}\t{count}")
except sqlite3.Error as exc:
    print(f"top_standards unavailable ({exc})")

conn.close()
PY
