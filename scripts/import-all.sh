#! /bin/bash

set -Eeuo pipefail

log() {
    echo "[import-all] $*"
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
make migrate-upgrade
make docker-redis
make docker-neo4j

RUN_COUNT="${RUN_COUNT:-1}"
log "Starting $RUN_COUNT worker(s)"
for i in $(seq 1 "$RUN_COUNT"); do
 (rm -f "worker-$i.log" && make start-worker &> "worker-$i.log")&
 done

[ -d "./venv" ] && . ./venv/bin/activate

if [[ -z "${CRE_SKIP_IMPORT_CORE:-}" ]]; then
    echo "CRE_SKIP_IMPORT_CORE is not set, importing core csv"
    python cre.py --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg
fi
if [[ -z "${CRE_SKIP_IMPORT_PROJECTS:-}" ]]; then
    echo "CRE_SKIP_IMPORT_PROJECTS is not set, importing external projects"
    echo "Importing CWE"
    python cre.py --cwe_in
    echo "Importing CAPEC"
    python cre.py --capec_in
    echo "Importing SECURE HEADERS"
    python cre.py --owasp_secure_headers_in
    echo "Importing PCI DSS 4"
    python cre.py --pci_dss_4_in
    echo "Importing Juiceshop"
    python cre.py --juiceshop_in
    echo "Importing DSOMM"
    python cre.py --dsomm_in
    echo "Importing ZAP"
    python cre.py --zap_in
    echo "Importing CheatSheets"
    python cre.py --cheatsheets_in
    echo "Importing Github Tools"
    python cre.py --github_tools_in
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
log "Import-all completed"
    
