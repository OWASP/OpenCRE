#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_SCRIPT_NAME="db-sync-local-to-opencreorg"
DEFAULT_HEROKU_APP="opencreorg"
BACKUP_LABEL="${BACKUP_LABEL:-sync-local-to-opencreorg}"
BACKUP_MANDATORY="${BACKUP_MANDATORY:-1}"

# shellcheck source=scripts/db/common.sh
source "${SCRIPT_DIR}/common.sh"

SOURCE_DB_URL="${SOURCE_DB_URL:-postgresql://cre:password@127.0.0.1:5432/cre}"
DUMP_FILE="${DUMP_FILE:-$(pwd)/tmp/opencre-local-sync.dump}"
PG_CLIENT_IMAGE="${PG_CLIENT_IMAGE:-postgres:18}"
RESET_TARGET_PUBLIC_SCHEMA="${RESET_TARGET_PUBLIC_SCHEMA:-1}"
SYNC_TABLES="${SYNC_TABLES:-all}"

usage() {
  cat <<'EOF'
Usage:
  APP_NAME=opencreorg SOURCE_DB_URL=postgresql://... scripts/db/sync-local-to-opencreorg.sh [--table node]...

Description:
  Sync local Postgres data into a Heroku app, while always capturing and waiting
  for a fresh backup before any restore.

Options:
  --table <table_name>     Repeatable. Limits sync to selected table(s), e.g. --table node
                           If omitted, full DB sync is used.
EOF
}

SYNC_TABLE_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --table)
      shift
      [[ $# -gt 0 ]] || die "--table requires a value"
      SYNC_TABLE_ARGS+=("$1")
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

if [[ ${#SYNC_TABLE_ARGS[@]} -gt 0 ]]; then
  SYNC_TABLES="$(IFS=,; echo "${SYNC_TABLE_ARGS[*]}")"
fi

require_tools
command -v docker >/dev/null 2>&1 || die "docker CLI not found"
ensure_heroku_auth

capture_backup_strict

dump_dir="$(dirname "${DUMP_FILE}")"
mkdir -p "${dump_dir}"

dump_cmd=(docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -v "${dump_dir}:${dump_dir}" \
  "${PG_CLIENT_IMAGE}" \
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file "${DUMP_FILE}")

if [[ "${SYNC_TABLES}" != "all" ]]; then
  IFS=',' read -r -a table_arr <<< "${SYNC_TABLES}"
  for table_name in "${table_arr[@]}"; do
    dump_cmd+=(--table "public.${table_name}")
  done
fi

dump_cmd+=("${SOURCE_DB_URL}")
log "Creating local dump from SOURCE_DB_URL (SYNC_TABLES=${SYNC_TABLES})"
"${dump_cmd[@]}"

app_db_url="$(resolve_app_database_url)"
if [[ "${app_db_url}" != *"sslmode="* ]]; then
  if [[ "${app_db_url}" == *"?"* ]]; then
    app_db_url="${app_db_url}&sslmode=require"
  else
    app_db_url="${app_db_url}?sslmode=require"
  fi
fi

if [[ "${RESET_TARGET_PUBLIC_SCHEMA}" == "1" && "${SYNC_TABLES}" == "all" ]]; then
  log "Resetting target public schema before restore"
  docker run --rm --network host "${PG_CLIENT_IMAGE}" \
    psql "${app_db_url}" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
fi

restore_cmd=(docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -v "${dump_dir}:${dump_dir}:ro" \
  "${PG_CLIENT_IMAGE}" \
  pg_restore \
    --no-owner \
    --no-privileges \
    --exit-on-error)

if [[ "${SYNC_TABLES}" != "all" ]]; then
  restore_cmd+=(--clean --if-exists)
fi

restore_cmd+=(--dbname "${app_db_url}" "${DUMP_FILE}")
log "Restoring dump into ${APP_NAME}"
"${restore_cmd[@]}"

log "Sync complete for app ${APP_NAME}. Verify with: heroku pg:info -a ${APP_NAME}"

