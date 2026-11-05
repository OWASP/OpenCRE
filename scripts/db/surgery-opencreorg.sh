#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_SCRIPT_NAME="db-surgery-opencreorg"
DEFAULT_HEROKU_APP="opencreorg"
BACKUP_LABEL="${BACKUP_LABEL:-surgery-opencreorg}"
BACKUP_MANDATORY="${BACKUP_MANDATORY:-1}"

# shellcheck source=scripts/db/common.sh
source "${SCRIPT_DIR}/common.sh"

CONFIRM_DESTRUCTIVE="${CONFIRM_DESTRUCTIVE:-}"
DESTRUCTIVE_CONFIRMATION_PHRASE="I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION"
SQL_FILE=""
ALLOW_DESTRUCTIVE=0

usage() {
  cat <<'EOF'
Usage:
  APP_NAME=opencreorg scripts/db/surgery-opencreorg.sh --sql-file path/to/change.sql [--destructive]

Description:
  Execute targeted SQL surgery against Heroku Postgres (for node add/remove/alter
  or other surgical fixes). A fresh backup is always captured and completed first.

Flags:
  --sql-file <path>        Required. SQL file to execute.
  --destructive            Required for DELETE/DROP/TRUNCATE/irreversible changes.
                           Also requires CONFIRM_DESTRUCTIVE to exactly equal:
                           I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sql-file)
      shift
      [[ $# -gt 0 ]] || die "--sql-file requires a value"
      SQL_FILE="$1"
      ;;
    --destructive)
      ALLOW_DESTRUCTIVE=1
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

[[ -n "${SQL_FILE}" ]] || die "--sql-file is required"
[[ -f "${SQL_FILE}" ]] || die "SQL file does not exist: ${SQL_FILE}"

require_tools
ensure_heroku_auth

if [[ "${ALLOW_DESTRUCTIVE}" == "1" ]]; then
  validate_uppercase_confirmation "${DESTRUCTIVE_CONFIRMATION_PHRASE}" "${CONFIRM_DESTRUCTIVE}"
fi

capture_backup_strict
run_sql_file "${SQL_FILE}"

log "Surgery complete for app ${APP_NAME}. Verify with: heroku pg:psql -a ${APP_NAME}"

