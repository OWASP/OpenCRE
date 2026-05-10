#!/usr/bin/env bash

set -euo pipefail

log() {
  echo "[push-local-postgres-to-heroku] $*"
}

die() {
  echo "[push-local-postgres-to-heroku] ERROR: $*" >&2
  exit 1
}

# Required:
#   APP_NAME                     Heroku app name (staging or prod)
#
# Backward compatibility:
#   STAGING_APP                  Legacy alias for APP_NAME
#
# Optional:
#   SOURCE_DB_URL                Local source Postgres URL
#                                default: postgresql://cre:password@127.0.0.1:5432/cre
#   DUMP_FILE                    Local dump path
#                                default: ./tmp/opencre-local-full.dump
#   PG_CLIENT_IMAGE              Docker image with pg_dump/pg_restore
#                                default: auto-detect from source DB (postgres:<major>)
#   CAPTURE_BACKUP               1 to capture Heroku backup first (default: 1)
#   SYNC_PROD_DATABASE_URL       1 to set PROD_DATABASE_URL to app DATABASE_URL (default: 1)
#   DUMP_PARALLEL_JOBS           Optional pg_dump -j (directory format only; ignored here)
#   STOP_STUCK_SETUP_SCRIPT      1 to stop stuck setup-heroku-staging.sh / pgloader (default: 1)
#   RESET_TARGET_PUBLIC_SCHEMA   1 to drop/recreate public schema before restore (default: 1)
#   SYNC_TABLES                  all|embeddings|gap_analysis|embeddings,gap_analysis (default: all)
#
# CLI flags (override SYNC_TABLES):
#   --embeddings                 sync only public.embeddings
#   --gap_analysis               sync only public.gap_analysis_results

APP_NAME="${APP_NAME:-${STAGING_APP:-}}"
SOURCE_DB_URL="${SOURCE_DB_URL:-postgresql://cre:password@127.0.0.1:5432/cre}"
DUMP_FILE="${DUMP_FILE:-}"
PG_CLIENT_IMAGE="${PG_CLIENT_IMAGE:-}"
CAPTURE_BACKUP="${CAPTURE_BACKUP:-1}"
SYNC_PROD_DATABASE_URL="${SYNC_PROD_DATABASE_URL:-1}"
STOP_STUCK_SETUP_SCRIPT="${STOP_STUCK_SETUP_SCRIPT:-1}"
RESET_TARGET_PUBLIC_SCHEMA="${RESET_TARGET_PUBLIC_SCHEMA:-1}"
SYNC_TABLES="${SYNC_TABLES:-all}"

SYNC_EMBEDDINGS=0
SYNC_GAP_ANALYSIS=0

for arg in "$@"; do
  case "${arg}" in
    --embeddings)
      SYNC_EMBEDDINGS=1
      ;;
    --gap_analysis)
      SYNC_GAP_ANALYSIS=1
      ;;
    *)
      die "Unknown argument: ${arg} (supported: --embeddings, --gap_analysis)"
      ;;
  esac
done

if [[ "${SYNC_EMBEDDINGS}" == "1" || "${SYNC_GAP_ANALYSIS}" == "1" ]]; then
  if [[ "${SYNC_EMBEDDINGS}" == "1" && "${SYNC_GAP_ANALYSIS}" == "1" ]]; then
    SYNC_TABLES="embeddings,gap_analysis"
  elif [[ "${SYNC_EMBEDDINGS}" == "1" ]]; then
    SYNC_TABLES="embeddings"
  else
    SYNC_TABLES="gap_analysis"
  fi
fi

if [[ "${SYNC_TABLES}" == "all" ]]; then
  SCOPE_ALL=1
elif [[ "${SYNC_TABLES}" == "embeddings" ]]; then
  SCOPE_ALL=0
  SYNC_EMBEDDINGS=1
  SYNC_GAP_ANALYSIS=0
elif [[ "${SYNC_TABLES}" == "gap_analysis" ]]; then
  SCOPE_ALL=0
  SYNC_EMBEDDINGS=0
  SYNC_GAP_ANALYSIS=1
elif [[ "${SYNC_TABLES}" == "embeddings,gap_analysis" || "${SYNC_TABLES}" == "gap_analysis,embeddings" ]]; then
  SCOPE_ALL=0
  SYNC_EMBEDDINGS=1
  SYNC_GAP_ANALYSIS=1
else
  die "Invalid SYNC_TABLES='${SYNC_TABLES}' (expected all|embeddings|gap_analysis|embeddings,gap_analysis)"
fi

[[ -n "${APP_NAME}" ]] || die "APP_NAME is required (or legacy STAGING_APP)"

command -v docker >/dev/null 2>&1 || die "docker CLI not found"
command -v heroku >/dev/null 2>&1 || die "heroku CLI not found"

if ! heroku auth:whoami >/dev/null 2>&1; then
  die "Not logged in to Heroku. Run: heroku login"
fi

if [[ "${STOP_STUCK_SETUP_SCRIPT}" == "1" ]]; then
  log "Stopping any stuck setup-heroku-staging / pgloader processes"
  pids="$(ps -eo pid,cmd | awk '/setup-heroku-staging\.sh|pgloader/ {print $1}' | tr '\n' ' ')"
  if [[ -n "${pids// }" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
fi

if [[ "${CAPTURE_BACKUP}" == "1" ]]; then
  log "Capturing app backup before restore"
  heroku pg:backups:capture -a "${APP_NAME}"
fi

log "Resolving app DATABASE_URL"
APP_DB_URL="$(heroku config:get DATABASE_URL -a "${APP_NAME}")"
[[ -n "${APP_DB_URL}" ]] || die "Failed to resolve DATABASE_URL for ${APP_NAME}"

APP_DB_URL_SSL="${APP_DB_URL}"
if [[ "${APP_DB_URL_SSL}" == *"sslmode="* ]]; then
  :
elif [[ "${APP_DB_URL_SSL}" == *"?"* ]]; then
  APP_DB_URL_SSL="${APP_DB_URL_SSL}&sslmode=require"
else
  APP_DB_URL_SSL="${APP_DB_URL_SSL}?sslmode=require"
fi

SOURCE_DB_URL_NO_SSL="${SOURCE_DB_URL}"
if [[ "${SOURCE_DB_URL_NO_SSL}" == *"sslmode="* ]]; then
  :
elif [[ "${SOURCE_DB_URL_NO_SSL}" == *"?"* ]]; then
  SOURCE_DB_URL_NO_SSL="${SOURCE_DB_URL_NO_SSL}&sslmode=disable"
else
  SOURCE_DB_URL_NO_SSL="${SOURCE_DB_URL_NO_SSL}?sslmode=disable"
fi

detect_source_pg_major() {
  local probe_image="${1:-postgres:18}"
  local ver_num=""
  set +e
  ver_num="$(
    docker run --rm --network host "${probe_image}" \
      psql "${SOURCE_DB_URL_NO_SSL}" -Atc "show server_version_num;" 2>/dev/null
  )"
  local rc=$?
  set -e
  if [[ ${rc} -ne 0 || -z "${ver_num}" ]]; then
    return 1
  fi
  echo $((ver_num / 10000))
}

if [[ -z "${PG_CLIENT_IMAGE}" ]]; then
  if major="$(detect_source_pg_major "postgres:18")"; then
    PG_CLIENT_IMAGE="postgres:${major}"
  else
    PG_CLIENT_IMAGE="postgres:18"
  fi
fi
log "Using Docker Postgres client image: ${PG_CLIENT_IMAGE}"

if [[ -z "${DUMP_FILE}" ]]; then
  DUMP_FILE="$(pwd)/tmp/opencre-local-full.dump"
fi

dump_dir="$(dirname "${DUMP_FILE}")"
dump_base="$(basename "${DUMP_FILE}")"
mkdir -p "${dump_dir}"

if ! touch "${DUMP_FILE}" 2>/dev/null; then
  DUMP_FILE="$(pwd)/tmp/opencre-local-full.dump"
  dump_dir="$(dirname "${DUMP_FILE}")"
  dump_base="$(basename "${DUMP_FILE}")"
  mkdir -p "${dump_dir}"
  touch "${DUMP_FILE}" || die "Cannot write dump file at ${DUMP_FILE}"
fi

dump_cmd=(docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -v "${dump_dir}:${dump_dir}" \
  "${PG_CLIENT_IMAGE}" \
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
  --file "${DUMP_FILE}")

if [[ "${SCOPE_ALL}" != "1" ]]; then
  if [[ "${SYNC_EMBEDDINGS}" == "1" ]]; then
    dump_cmd+=(--table public.embeddings)
  fi
  if [[ "${SYNC_GAP_ANALYSIS}" == "1" ]]; then
    dump_cmd+=(--table public.gap_analysis_results)
  fi
fi
dump_cmd+=("${SOURCE_DB_URL_NO_SSL}")

if [[ "${SCOPE_ALL}" == "1" ]]; then
  log "Dumping full local source DB via Docker pg_dump"
else
  log "Dumping selected tables from local source DB via Docker pg_dump (SYNC_TABLES=${SYNC_TABLES})"
fi
"${dump_cmd[@]}"

log "Restoring dump into Heroku app via Docker pg_restore"
if [[ "${RESET_TARGET_PUBLIC_SCHEMA}" == "1" && "${SCOPE_ALL}" == "1" ]]; then
  log "Resetting target public schema (DROP SCHEMA public CASCADE; CREATE SCHEMA public)"
  docker run --rm --network host \
    "${PG_CLIENT_IMAGE}" \
    psql "${APP_DB_URL_SSL}" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
elif [[ "${RESET_TARGET_PUBLIC_SCHEMA}" == "1" && "${SCOPE_ALL}" != "1" ]]; then
  log "RESET_TARGET_PUBLIC_SCHEMA=1 ignored for table-scoped sync (SYNC_TABLES=${SYNC_TABLES})"
fi

restore_cmd=(docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -v "${dump_dir}:${dump_dir}:ro" \
  "${PG_CLIENT_IMAGE}" \
  pg_restore \
    --no-owner \
    --no-privileges \
  --exit-on-error)

if [[ "${SCOPE_ALL}" != "1" ]]; then
  restore_cmd+=(--clean --if-exists)
fi
restore_cmd+=(--dbname "${APP_DB_URL_SSL}" "${dump_dir}/${dump_base}")
"${restore_cmd[@]}"

if [[ "${SYNC_PROD_DATABASE_URL}" == "1" ]]; then
  log "Syncing PROD_DATABASE_URL to app DATABASE_URL (SQLAlchemy-safe)"
  SQLA_URL="${APP_DB_URL/#postgres:\/\//postgresql://}"
  heroku config:set -a "${APP_NAME}" "PROD_DATABASE_URL=${SQLA_URL}" >/dev/null
fi

if [[ "${SCOPE_ALL}" == "1" ]]; then
  log "Done. App DB replaced from local Postgres source."
else
  log "Done. App DB updated from local Postgres source (SYNC_TABLES=${SYNC_TABLES})."
fi
log "Quick verify: heroku pg:info -a ${APP_NAME}"
