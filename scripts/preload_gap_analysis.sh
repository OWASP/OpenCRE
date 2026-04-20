#!/usr/bin/env bash

set -Eeuo pipefail

log() {
    echo "[preload_gap_analysis] $*"
}

RUN_COUNT="${RUN_COUNT:-5}"
PORT="${PORT:-5000}"
USE_POSTGRES="${CRE_PRELOAD_USE_POSTGRES:-1}"
POSTGRES_URL="${POSTGRES_URL:-postgresql://cre:password@127.0.0.1:5432/cre}"
SEED_FROM_SQLITE="${CRE_PRELOAD_SEED_FROM_SQLITE:-1}"
SQLITE_SEED_PATH="${CRE_PRELOAD_SQLITE_PATH:-$(pwd)/standards_cache.sqlite}"

export NEO4J_URL="${NEO4J_URL:-bolt://neo4j:password@127.0.0.1:7687}"
export FLASK_APP="$(pwd)/cre.py"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
    if [[ -x "./venv/bin/python" ]]; then
        PYTHON_BIN="./venv/bin/python"
    else
        PYTHON_BIN="$(command -v python3 || true)"
    fi
fi
if [[ -z "${PYTHON_BIN}" ]]; then
    log "No python interpreter found (set PYTHON_BIN or install python3)"
    exit 1
fi

# Pair-GA jobs require Postgres backend. Default preload to local Postgres.
if [[ "${USE_POSTGRES}" == "1" ]]; then
    export PROD_DATABASE_URL="${PROD_DATABASE_URL:-${POSTGRES_URL}}"
    export CRE_CACHE_FILE="${CRE_CACHE_FILE:-${POSTGRES_URL}}"
fi

worker_pids=()
flask_pid=""

cleanup() {
    set +e
    for pid in "${worker_pids[@]:-}"; do
        kill "${pid}" 2>/dev/null || true
    done
    if [[ -n "${flask_pid}" ]]; then
        kill "${flask_pid}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

seed_postgres_from_sqlite_if_empty() {
    if [[ "${USE_POSTGRES}" != "1" || "${SEED_FROM_SQLITE}" != "1" ]]; then
        return 0
    fi
    if [[ ! -f "${SQLITE_SEED_PATH}" ]]; then
        log "SQLite seed file not found at ${SQLITE_SEED_PATH}; skipping seed"
        return 0
    fi

    "${PYTHON_BIN}" - <<'PY' "${POSTGRES_URL}" "${SQLITE_SEED_PATH}"
import json
import sqlite3
import sys
from datetime import date, datetime, time
from decimal import Decimal

import psycopg2

pg_url = sys.argv[1]
sqlite_path = sys.argv[2]

target_tables = [
    "alembic_version",
    "cre",
    "cre_links",
    "cre_node_links",
    "gap_analysis_results",
    "import_run",
    "node",
    "staged_change_set",
    "standard_snapshot",
]

def normalize_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value

pg = psycopg2.connect(pg_url)
pg.autocommit = True
pc = pg.cursor()

pc.execute("SELECT to_regclass('public.node')")
if pc.fetchone()[0] is None:
    print("[preload_gap_analysis] Postgres schema not ready (node table missing); skipping seed")
    pc.close()
    pg.close()
    sys.exit(0)

pc.execute("SELECT COUNT(*) FROM public.node")
node_count = int(pc.fetchone()[0])
if node_count > 0:
    print(f"[preload_gap_analysis] Postgres already populated (node rows={node_count}); skipping SQLite seed")
    pc.close()
    pg.close()
    sys.exit(0)

sc = sqlite3.connect(sqlite_path)
sc.row_factory = sqlite3.Row
scur = sc.cursor()

seeded_tables = 0
for table in target_tables:
    scur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    if scur.fetchone() is None:
        continue

    scur.execute(f'PRAGMA table_info("{table}")')
    cols = [row[1] for row in scur.fetchall()]
    if not cols:
        continue

    quoted_cols = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql = (
        f'INSERT INTO public."{table}" ({quoted_cols}) '
        f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    )

    scur.execute(f'SELECT {quoted_cols} FROM "{table}"')
    rows = scur.fetchall()
    if not rows:
        continue

    values = [tuple(normalize_value(v) for v in row) for row in rows]
    pc.executemany(insert_sql, values)
    seeded_tables += 1

print(f"[preload_gap_analysis] Seeded Postgres from SQLite ({seeded_tables} table(s))")

sc.close()
pc.close()
pg.close()
PY

    # Keep embeddings sync aligned with the dedicated cross-backend script.
    "${PYTHON_BIN}" scripts/sync_embeddings_table.py \
      --from-sqlite "${SQLITE_SEED_PATH}" \
      --to-postgres "${POSTGRES_URL}" \
      --require-local-destination
}

make docker-redis
make docker-neo4j
if [[ "${USE_POSTGRES}" == "1" ]]; then
    make docker-postgres
fi
make migrate-upgrade
seed_postgres_from_sqlite_if_empty

for i in $(seq 1 "${RUN_COUNT}"); do
    (
        rm -f "worker-${i}.log"
        make start-worker &> "worker-${i}.log"
    ) &
    worker_pids+=("$!")
done

[ -d "./venv" ] && . ./venv/bin/activate
rm -f gap_analysis_flask.log
make dev-flask PORT="${PORT}" &> gap_analysis_flask.log &
flask_pid=$!

sleep 5

"${PYTHON_BIN}" cre.py --preload_map_analysis_target_url "http://127.0.0.1:${PORT}"
log "Map analysis preload completed"
    
