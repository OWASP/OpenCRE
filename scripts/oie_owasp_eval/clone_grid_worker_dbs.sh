#!/bin/zsh
# Clone local `cre` into isolated Module C switch-grid worker DBs.
#
# Default: cre_grid_w0 .. cre_grid_w3 via CREATE DATABASE … TEMPLATE.
# Source DB (~500MB with embeddings) must have zero other connections.
#
# Usage:
#   scripts/oie_owasp_eval/clone_grid_worker_dbs.sh
#   WORKERS=4 SOURCE_DB=cre scripts/oie_owasp_eval/clone_grid_worker_dbs.sh
#   FORCE=1 …   # drop existing cre_grid_w* first
set -euo pipefail

SOURCE_DB="${SOURCE_DB:-cre}"
WORKERS="${WORKERS:-4}"
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5432}"
USER="${PGUSER:-cre}"
export PGPASSWORD="${PGPASSWORD:-password}"
PREFIX="${DB_PREFIX:-cre_grid_w}"

psql_admin() {
  psql -h "$HOST" -p "$PORT" -U "$USER" -d postgres -v ON_ERROR_STOP=1 "$@"
}

echo "=== clone_grid_worker_dbs source=$SOURCE_DB workers=$WORKERS ==="

size=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$SOURCE_DB" -tAc \
  "SELECT pg_size_pretty(pg_database_size(current_database()))")
echo "SOURCE_SIZE $SOURCE_DB = $size"

# Terminate other sessions on source (required for TEMPLATE clone).
echo "TERMINATE backends on $SOURCE_DB (except this session)"
psql_admin -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$SOURCE_DB'
  AND pid <> pg_backend_pid();
" >/dev/null

for i in $(seq 0 $((WORKERS - 1))); do
  name="${PREFIX}${i}"
  exists=$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$name'" | tr -d '[:space:]')
  if [[ "$exists" == "1" ]]; then
    if [[ "${FORCE:-0}" == "1" ]]; then
      echo "DROP $name (FORCE=1)"
      psql_admin -c "
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '$name' AND pid <> pg_backend_pid();
      " >/dev/null || true
      psql_admin -c "DROP DATABASE IF EXISTS ${name};"
    else
      echo "KEEP $name (already exists; set FORCE=1 to recreate)"
      continue
    fi
  fi
  echo "CREATE $name TEMPLATE $SOURCE_DB …"
  t0=$(date +%s)
  psql_admin -c "CREATE DATABASE ${name} TEMPLATE ${SOURCE_DB} OWNER ${USER};"
  t1=$(date +%s)
  wsize=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$name" -tAc \
    "SELECT pg_size_pretty(pg_database_size(current_database()))")
  kq=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$name" -tAc \
    "SELECT count(*) FROM knowledge_queue WHERE pipeline_run_id='orch-exp-baseline-20260921'")
  echo "OK $name size=$wsize kq_harvest=$kq elapsed=$((t1 - t0))s"
done

echo "=== DONE worker DBs: ${PREFIX}0 .. ${PREFIX}$((WORKERS - 1)) ==="
echo "Each worker uses DEV_DATABASE_URL=postgresql://${USER}:***@${HOST}:${PORT}/${PREFIX}N"
echo "Same pipeline_run_id orch-exp-baseline-20260921 per DB (isolated decision_queue)."
