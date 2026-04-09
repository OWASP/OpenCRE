#! /bin/bash

set -Eeuo pipefail

log() {
    echo "[import-all] $*"
}

export_postgres_to_sqlite() {
    local pg_url="$1"
    local sqlite_path="$2"
    log "Exporting Postgres data to sqlite at ${sqlite_path}"
    python - <<'PY' "${pg_url}" "${sqlite_path}"
import sqlite3
import sys
from typing import List, Tuple

import psycopg2

pg_url = sys.argv[1]
sqlite_path = sys.argv[2]

pg = psycopg2.connect(pg_url)
pg.autocommit = True
pg_cur = pg.cursor()

tables: List[str] = [
    "alembic_version",
    "cre",
    "cre_links",
    "cre_node_links",
    "embeddings",
    "gap_analysis_results",
    "import_run",
    "node",
    "staged_change_set",
    "standard_snapshot",
]

type_rows: List[Tuple[str, str, str]] = []
for t in tables:
    pg_cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (t,),
    )
    cols = pg_cur.fetchall()
    type_rows.append((t, "", ""))
    type_rows.extend((t, c[0], c[1]) for c in cols)

def map_type(dtype: str) -> str:
    d = (dtype or "").lower()
    if "int" in d:
        return "INTEGER"
    if d in ("numeric", "real", "double precision", "decimal"):
        return "REAL"
    if d in ("boolean",):
        return "INTEGER"
    return "TEXT"

sqlite = sqlite3.connect(sqlite_path)
scur = sqlite.cursor()

for table in tables:
    pg_cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    cols = pg_cur.fetchall()
    if not cols:
        continue

    scur.execute(f'DROP TABLE IF EXISTS "{table}"')
    col_defs = ", ".join([f'"{c}" {map_type(t)}' for c, t in cols])
    scur.execute(f'CREATE TABLE "{table}" ({col_defs})')

    col_names = [c for c, _ in cols]
    quoted_cols = ", ".join([f'"{c}"' for c in col_names])
    pg_cur.execute(f'SELECT {quoted_cols} FROM public."{table}"')
    rows = pg_cur.fetchall()
    if rows:
        placeholders = ", ".join(["?"] * len(col_names))
        scur.executemany(
            f'INSERT INTO "{table}" ({quoted_cols}) VALUES ({placeholders})',
            rows,
        )

sqlite.commit()
sqlite.close()
pg_cur.close()
pg.close()
print(f"Copied {len(tables)} tables from Postgres to {sqlite_path}")
PY
}

trap 'log "FAILED at line $LINENO: ${BASH_COMMAND}"' ERR

log "Starting import-all script"
if [[ -f .env ]]; then
    log "Loading and exporting variables from .env"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
else
    log "No .env file found; using existing environment"
fi

export OpenCRE_gspread_Auth='service_account'
export GOOGLE_PROJECT_ID='opencre-vertex'
export NEO4J_URL='neo4j://neo4j:password@127.0.0.1:7687'
export FLASK_APP="$(pwd)/cre.py"

if [[ -n "${SVC_ACC_KEY_PATH:-}" ]]; then
    log "Loading service account credentials from SVC_ACC_KEY_PATH"
    export SERVICE_ACCOUNT_CREDENTIALS="$(cat "${SVC_ACC_KEY_PATH}")"
else
    log "SVC_ACC_KEY_PATH not set (core spreadsheet import may fail if enabled)"
fi

if docker ps --format '{{.Names}}' | grep -q '^cre-neo4j$'; then
    log "Stopping existing neo4j container"
    docker stop cre-neo4j
    make docker-neo4j-rm
fi

if docker ps --format '{{.Names}}' | grep -q '^cre-redis-stack$'; then
    log "Stopping existing redis container"
    docker stop cre-redis-stack
fi

if [[ -n "${CRE_DELETE_DB:-}" ]]; then
    echo "CRE_DELETE_DB is set, emptying database"
    rm -rf standards_cache.sqlite
fi

log "Running migrations and starting infra"
USE_POSTGRES=0
RUN_COUNT="${RUN_COUNT:-1}"
IMPORT_CACHE_FILE="standards_cache.sqlite"
if [[ "${RUN_COUNT}" -gt 1 ]]; then
    USE_POSTGRES=1
    POSTGRES_URL="${POSTGRES_URL:-postgresql://cre:password@127.0.0.1:5432/cre}"
    log "RUN_COUNT=${RUN_COUNT} (>1), using docker postgres for imports"
    make docker-postgres
    export PROD_DATABASE_URL="${POSTGRES_URL}"
    IMPORT_CACHE_FILE="${POSTGRES_URL}"
fi

make migrate-upgrade
make docker-redis
make docker-neo4j

log "Starting $RUN_COUNT worker(s)"
for i in $(seq 1 "$RUN_COUNT"); do
 (rm -f "worker-$i.log" && make start-worker &> "worker-$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate

if [[ -z "${CRE_SKIP_IMPORT_CORE:-}" ]]; then
    echo "CRE_SKIP_IMPORT_CORE is not set, importing core csv"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
fi
if [[ -z "${CRE_SKIP_IMPORT_PROJECTS:-}" ]]; then
    echo "CRE_SKIP_IMPORT_PROJECTS is not set, importing external projects"
    if [[ -n "${CRE_AI_EXCHANGE_CSV_PATH:-}" ]]; then
        echo "Importing OWASP AI Exchange / MITRE ATLAS from CSV"
        python cre.py --cache_file "${IMPORT_CACHE_FILE}" --add --from_ai_exchange_csv "${CRE_AI_EXCHANGE_CSV_PATH}"
    else
        echo "Skipping OWASP AI Exchange / MITRE ATLAS import (set CRE_AI_EXCHANGE_CSV_PATH to enable)"
    fi
    echo "Importing CWE"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --cwe_in
    echo "Importing CAPEC"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --capec_in
    echo "Importing SECURE HEADERS"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --owasp_secure_headers_in
    echo "Importing PCI DSS 4"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --pci_dss_4_in
    echo "Importing Juiceshop"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --juiceshop_in
    echo "Importing DSOMM"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --dsomm_in
    echo "Importing ZAP"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --zap_in
    echo "Importing CheatSheets"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --cheatsheets_in
    echo "Importing Github Tools"
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" --github_tools_in
fi

log "Stopping workers"
# RQ workers run under `make start-worker`; SIGTERM yields make exit != 0. Reap those
# jobs without firing ERR / set -e (import already succeeded).
set +e
trap - ERR
if pgrep -x python >/dev/null; then
    killall python 2>/dev/null || true
fi
if pgrep -x make >/dev/null; then
    killall make 2>/dev/null || true
fi
wait || true
set -e
trap 'log "FAILED at line $LINENO: ${BASH_COMMAND}"' ERR

if [[ "${USE_POSTGRES}" == "1" ]]; then
    export_postgres_to_sqlite "${POSTGRES_URL}" "standards_cache.sqlite"
fi

log "Import-all completed"
    
