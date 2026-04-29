#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_SCRIPT_NAME="db-backup-opencreorg"
DEFAULT_HEROKU_APP="opencreorg"
BACKUP_LABEL="${BACKUP_LABEL:-manual-backup-opencreorg}"
BACKUP_MANDATORY="${BACKUP_MANDATORY:-1}"

# shellcheck source=scripts/db/common.sh
source "${SCRIPT_DIR}/common.sh"

require_tools
ensure_heroku_auth
capture_backup_strict

log "Backup-only flow complete for ${APP_NAME}"

