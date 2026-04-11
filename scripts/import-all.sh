#! /bin/bash

set -Eeuo pipefail

log() {
    echo "[import-all] $*"
}

# Each importer flag must be a separate shell word: a line break inside e.g.
# ``--pci_dss_4_in`` would run ``_in`` as a command ("_in: command not found").
run_cre_import() {
    python cre.py --cache_file "${IMPORT_CACHE_FILE}" "$@"
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
DASHBOARD_PID=""

wait_for_neo4j() {
    local max_s="${CRE_NEO4J_READY_TIMEOUT_SECONDS:-180}"
    local waited=0
    log "Waiting for Neo4j to accept Bolt queries (timeout ${max_s}s)"
    while [[ "${waited}" -lt "${max_s}" ]]; do
        if docker exec cre-neo4j cypher-shell -u neo4j -p password --non-interactive "RETURN 1 AS ok;" &>/dev/null; then
            log "Neo4j ready after ${waited}s"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    log "Neo4j did not become ready within ${max_s}s"
    return 1
}

start_import_dashboard() {
    if [[ "${CRE_IMPORT_DASHBOARD:-0}" != "1" ]]; then
        return
    fi
    local dash_port="${CRE_IMPORT_DASHBOARD_PORT:-8765}"
    local dash_host="${CRE_IMPORT_DASHBOARD_HOST:-127.0.0.1}"
    local py="python"
    if [[ -x "./venv/bin/python" ]]; then
        py="./venv/bin/python"
    fi
    log "Starting import dashboard on http://${dash_host}:${dash_port}"
    log "Dashboard RQ GA queue: CRE_GA_QUEUE_NAME=${CRE_GA_QUEUE_NAME:-ga} (must match workers; default queue name is ga)"
    log "Open http://127.0.0.1:${dash_port}/ (root path only; /dashboard redirects to /)"
    ("${py}" "./scripts/import_dashboard.py" --host "${dash_host}" --port "${dash_port}" > import-dashboard.log 2>&1) &
    DASHBOARD_PID=$!
    sleep 1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${dash_port}/health" 2>/dev/null || echo "000")
    if [[ "${code}" != "200" ]]; then
        log "WARNING: dashboard health check returned HTTP ${code} (expected 200). Wrong port, another process on 127.0.0.1:${dash_port}, or crash — see import-dashboard.log"
    fi
    if command -v xdg-open >/dev/null 2>&1; then
        (xdg-open "http://127.0.0.1:${dash_port}/" >/dev/null 2>&1 || true) &
    fi
}

stop_import_dashboard() {
    if [[ -n "${DASHBOARD_PID:-}" ]]; then
        kill "${DASHBOARD_PID}" 2>/dev/null || true
        wait "${DASHBOARD_PID}" 2>/dev/null || true
        DASHBOARD_PID=""
    fi
}

trap stop_import_dashboard EXIT

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
export NEO4J_URL='bolt://neo4j:password@127.0.0.1:7687'
export FLASK_APP="$(pwd)/cre.py"
PRESERVE_INFRA="${CRE_PRESERVE_INFRA:-0}"

if [[ -n "${SVC_ACC_KEY_PATH:-}" ]]; then
    log "Loading service account credentials from SVC_ACC_KEY_PATH"
    export SERVICE_ACCOUNT_CREDENTIALS="$(cat "${SVC_ACC_KEY_PATH}")"
else
    log "SVC_ACC_KEY_PATH not set (core spreadsheet import may fail if enabled)"
fi

if [[ "${PRESERVE_INFRA}" == "1" ]]; then
    log "CRE_PRESERVE_INFRA=1; preserving existing Neo4j/Redis containers and Neo4j data volumes"
else
    if docker ps --format '{{.Names}}' | grep -q '^cre-neo4j$'; then
        log "Stopping existing neo4j container"
        docker stop cre-neo4j
        make docker-neo4j-rm
    fi

    if docker ps --format '{{.Names}}' | grep -q '^cre-redis-stack$'; then
        log "Stopping existing redis container"
        docker stop cre-redis-stack
    fi
fi

if [[ -n "${CRE_DELETE_DB:-}" ]]; then
    echo "CRE_DELETE_DB is set, emptying database"
    rm -rf standards_cache.sqlite
fi

log "Running migrations and starting infra"
USE_POSTGRES=0
RUN_COUNT="${RUN_COUNT:-1}"
IMPORT_CACHE_FILE="standards_cache.sqlite"

# Partition GA vs import workers (must run before Postgres gate so expanded RUN_COUNT still uses PG).
GA_WORKER_COUNT="${CRE_GA_WORKER_COUNT:-}"
if [[ -z "${GA_WORKER_COUNT}" ]]; then
    if [[ "${RUN_COUNT}" -gt 1 ]]; then
        GA_WORKER_COUNT=$(( RUN_COUNT / 3 ))
        if [[ "${GA_WORKER_COUNT}" -lt 1 ]]; then
            GA_WORKER_COUNT=1
        fi
    else
        GA_WORKER_COUNT=0
    fi
fi
if [[ -n "${CRE_GA_WORKER_COUNT:-}" && "${GA_WORKER_COUNT}" -gt "${RUN_COUNT}" ]]; then
    default_ga=$(( RUN_COUNT / 3 ))
    if [[ "${default_ga}" -lt 1 && "${RUN_COUNT}" -gt 1 ]]; then
        default_ga=1
    fi
    if [[ "${RUN_COUNT}" -le 1 ]]; then
        default_ga=0
    fi
    import_slots=$(( RUN_COUNT - default_ga ))
    if [[ "${import_slots}" -lt 1 ]]; then
        import_slots=1
    fi
    prev_run=${RUN_COUNT}
    RUN_COUNT=$(( GA_WORKER_COUNT + import_slots ))
    log "Expanded RUN_COUNT from ${prev_run} to ${RUN_COUNT} (CRE_GA_WORKER_COUNT=${GA_WORKER_COUNT}, ${import_slots} import worker(s))"
fi
if [[ "${GA_WORKER_COUNT}" -gt "${RUN_COUNT}" ]]; then
    GA_WORKER_COUNT="${RUN_COUNT}"
fi

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
wait_for_neo4j

log "Starting $RUN_COUNT worker(s)"
log "Worker queue partition: ga_workers=${GA_WORKER_COUNT}, import_workers=$((RUN_COUNT-GA_WORKER_COUNT))"
# Subshells inherit ERR/set -e; SIGTERM during shutdown makes ``make`` exit != 0 and
# would spam "[import-all] FAILED at line …" unless we disable ERR inside each worker.
for i in $(seq 1 "$RUN_COUNT"); do
 if [[ "${i}" -le "${GA_WORKER_COUNT}" ]]; then
    (
        set +e
        trap - ERR 2>/dev/null || true
        rm -f "worker-$i.log"
        CRE_WORKER_QUEUES="ga" make start-worker &> "worker-$i.log"
    ) &
 else
    (
        set +e
        trap - ERR 2>/dev/null || true
        rm -f "worker-$i.log"
        CRE_WORKER_QUEUES="high,default,low" make start-worker &> "worker-$i.log"
    ) &
 fi
 done

[ -d "./venv" ] && . ./venv/bin/activate

# Dashboard runs in a subshell: export DB vars so import_dashboard matches this script's --cache_file target.
# IMPORT_CACHE_FILE was a local variable only; workers used it via cre.py but the dashboard read PROD_DATABASE_URL / CRE_CACHE_FILE.
if [[ "${IMPORT_CACHE_FILE}" == *"://"* ]]; then
    export CRE_CACHE_FILE="${IMPORT_CACHE_FILE}"
else
    export CRE_CACHE_FILE="$(pwd)/${IMPORT_CACHE_FILE}"
fi
export PROD_DATABASE_URL="${PROD_DATABASE_URL:-${CRE_CACHE_FILE}}"

start_import_dashboard

if [[ -z "${CRE_SKIP_IMPORT_CORE:-}" ]]; then
    echo "CRE_SKIP_IMPORT_CORE is not set, importing core csv"
    run_cre_import --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
fi
if [[ -z "${CRE_SKIP_IMPORT_PROJECTS:-}" ]]; then
    echo "CRE_SKIP_IMPORT_PROJECTS is not set, importing external projects"
    if [[ -n "${CRE_AI_EXCHANGE_CSV_PATH:-}" ]]; then
        echo "Importing OWASP AI Exchange / MITRE ATLAS from CSV"
        run_cre_import --add --from_ai_exchange_csv "${CRE_AI_EXCHANGE_CSV_PATH}"
    else
        echo "Skipping OWASP AI Exchange / MITRE ATLAS import (set CRE_AI_EXCHANGE_CSV_PATH to enable)"
    fi
    echo "Importing CWE"
    run_cre_import --cwe_in
    echo "Importing CAPEC"
    run_cre_import --capec_in
    echo "Importing SECURE HEADERS"
    run_cre_import --owasp_secure_headers_in
    echo "Importing PCI DSS 4"
    run_cre_import --pci_dss_4_in
    echo "Importing Juiceshop"
    run_cre_import --juiceshop_in
    echo "Importing DSOMM"
    run_cre_import --dsomm_in
    echo "Importing ZAP"
    run_cre_import --zap_in
    echo "Importing CheatSheets"
    run_cre_import --cheatsheets_in
    echo "Importing Github Tools"
    run_cre_import --github_tools_in
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
    
