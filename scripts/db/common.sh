#!/usr/bin/env bash

set -euo pipefail

DB_SCRIPT_NAME="${DB_SCRIPT_NAME:-db-script}"
DEFAULT_HEROKU_APP="${DEFAULT_HEROKU_APP:-opencreorg}"
APP_NAME="${APP_NAME:-${HEROKU_APP:-${DEFAULT_HEROKU_APP}}}"
BACKUP_LABEL="${BACKUP_LABEL:-manual-db-op}"
BACKUP_MANDATORY="${BACKUP_MANDATORY:-1}"

log() {
  echo "[${DB_SCRIPT_NAME}] $*"
}

die() {
  echo "[${DB_SCRIPT_NAME}] ERROR: $*" >&2
  exit 1
}

require_tools() {
  command -v heroku >/dev/null 2>&1 || die "heroku CLI not found"
  command -v psql >/dev/null 2>&1 || die "psql not found"
}

ensure_heroku_auth() {
  if ! heroku auth:whoami >/dev/null 2>&1; then
    die "Not logged in to Heroku. Run: heroku login"
  fi
}

validate_uppercase_confirmation() {
  local confirmation_phrase="$1"
  local provided="${2:-}"
  if [[ "${provided}" != "${confirmation_phrase}" ]]; then
    die "Refusing destructive action. Set CONFIRM_DESTRUCTIVE='${confirmation_phrase}'"
  fi
}

capture_backup_strict() {
  if [[ "${BACKUP_MANDATORY}" != "1" ]]; then
    die "BACKUP_MANDATORY must remain 1 for production DB operations"
  fi

  log "Capturing Heroku backup for ${APP_NAME} (label=${BACKUP_LABEL})"
  heroku pg:backups:capture -a "${APP_NAME}" >/dev/null

  # Wait ensures the backup is completed before any DB mutation.
  heroku pg:backups:wait -a "${APP_NAME}" >/dev/null

  local latest_backup_info
  latest_backup_info="$(heroku pg:backups -a "${APP_NAME}" | sed -n '1,3p')"
  [[ -n "${latest_backup_info}" ]] || die "Could not verify backup output"
  log "Backup completed. Latest backup details:"
  echo "${latest_backup_info}"
}

resolve_app_database_url() {
  local db_url
  db_url="$(heroku config:get DATABASE_URL -a "${APP_NAME}")"
  [[ -n "${db_url}" ]] || die "Failed to resolve DATABASE_URL for ${APP_NAME}"
  echo "${db_url}"
}

run_sql_file() {
  local sql_file="$1"
  [[ -f "${sql_file}" ]] || die "SQL file does not exist: ${sql_file}"

  local db_url
  db_url="$(resolve_app_database_url)"

  log "Executing SQL file against ${APP_NAME}: ${sql_file}"
  PGPASSWORD="" psql "${db_url}" -v ON_ERROR_STOP=1 -f "${sql_file}"
}

