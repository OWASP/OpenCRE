#!/usr/bin/env bash

set -Eeuo pipefail

log() {
  echo "[backfill-gap-analysis] $*"
}

RUN_COUNT="${RUN_COUNT:-8}"
POSTGRES_URL="${POSTGRES_URL:-postgresql://cre:password@127.0.0.1:5432/cre}"
GA_BATCH_SIZE="${GA_BATCH_SIZE:-200}"
GA_POLL_SECONDS="${GA_POLL_SECONDS:-5}"
GA_MAX_PAIRS="${GA_MAX_PAIRS:-0}"
CLEAN_START="${GA_BACKFILL_CLEAN_START:-1}"

export NEO4J_URL="${NEO4J_URL:-bolt://neo4j:password@127.0.0.1:7687}"
export FLASK_APP="$(pwd)/cre.py"
export PROD_DATABASE_URL="${PROD_DATABASE_URL:-${POSTGRES_URL}}"
export CRE_CACHE_FILE="${CRE_CACHE_FILE:-${POSTGRES_URL}}"

worker_pids=()

cleanup() {
  set +e
  for pid in "${worker_pids[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT

if [[ "${CLEAN_START}" == "1" ]]; then
  log "Stopping stale worker/backfill processes"
  pkill -f "python cre.py --start_worker" 2>/dev/null || true
  pkill -f "cre.py --ga_backfill_missing" 2>/dev/null || true
fi

make docker-redis
make docker-neo4j
make docker-postgres
make migrate-upgrade

log "Starting ${RUN_COUNT} worker(s)"
for i in $(seq 1 "${RUN_COUNT}"); do
  (
    rm -f "worker-${i}.log"
    make start-worker &> "worker-${i}.log"
  ) &
  worker_pids+=("$!")
done

PYTHON_BIN="./.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="./venv/bin/python"
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

log "Running GA-only missing-pair backfill"
"${PYTHON_BIN}" cre.py \
  --cache_file "${POSTGRES_URL}" \
  --ga_backfill_missing \
  --ga_backfill_batch_size "${GA_BATCH_SIZE}" \
  --ga_backfill_poll_seconds "${GA_POLL_SECONDS}" \
  --ga_backfill_max_pairs "${GA_MAX_PAIRS}"

log "GA backfill finished"
