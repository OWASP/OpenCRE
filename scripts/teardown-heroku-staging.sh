#!/usr/bin/env bash

set -euo pipefail

log() {
  echo "[teardown-heroku-staging] $*"
}

die() {
  echo "[teardown-heroku-staging] ERROR: $*" >&2
  exit 1
}

# Required:
#   STAGING_APP            e.g. opencre-staging
#
# Optional:
#   STAGING_DOMAIN         e.g. staging.opencre.org
#   DESTROY_DB             1 to destroy Heroku Postgres addon(s) (default: 1)
#   DESTROY_APP            1 to destroy Heroku app (default: 0)
#   CONFIRM                must be "yes" for destructive actions
#   REMOVE_DOMAIN_ONLY     1 to remove domain and exit (default: 0)

STAGING_APP="${STAGING_APP:-}"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.opencre.org}"
DESTROY_DB="${DESTROY_DB:-1}"
DESTROY_APP="${DESTROY_APP:-0}"
REMOVE_DOMAIN_ONLY="${REMOVE_DOMAIN_ONLY:-0}"
CONFIRM="${CONFIRM:-}"

[[ -n "${STAGING_APP}" ]] || die "STAGING_APP is required"

command -v heroku >/dev/null 2>&1 || die "heroku CLI not found"

if ! heroku auth:whoami >/dev/null 2>&1; then
  die "Not logged in to Heroku. Run: heroku login"
fi

if ! heroku apps:info -a "${STAGING_APP}" >/dev/null 2>&1; then
  die "Heroku app not found: ${STAGING_APP}"
fi

remove_domain_if_present() {
  if heroku domains -a "${STAGING_APP}" | grep -qE "(^|[[:space:]])${STAGING_DOMAIN}([[:space:]]|$)"; then
    log "Removing domain ${STAGING_DOMAIN} from ${STAGING_APP}"
    heroku domains:remove "${STAGING_DOMAIN}" -a "${STAGING_APP}"
  else
    log "Domain not attached (nothing to remove): ${STAGING_DOMAIN}"
  fi
}

destroy_postgres_addons_if_present() {
  local addons_json
  local pg_addons

  addons_json="$(heroku addons -a "${STAGING_APP}" --json)"
  pg_addons="$(python3 - <<'PY' "${addons_json}"
import json
import sys

addons = json.loads(sys.argv[1])
names = []
for addon in addons:
    service = (addon.get("addon_service") or {}).get("name")
    if service == "heroku-postgresql":
        name = addon.get("name")
        if name:
            names.append(name)
print("\n".join(names))
PY
)"

  if [[ -z "${pg_addons}" ]]; then
    log "No Heroku Postgres addons found on ${STAGING_APP}"
    return
  fi

  if [[ "${CONFIRM}" != "yes" ]]; then
    die "Refusing to destroy DB without CONFIRM=yes"
  fi

  while IFS= read -r addon; do
    [[ -n "${addon}" ]] || continue
    log "Destroying Postgres addon ${addon} on ${STAGING_APP}"
    heroku addons:destroy "${addon}" -a "${STAGING_APP}" --confirm "${STAGING_APP}"
  done <<< "${pg_addons}"
}

remove_domain_if_present

if [[ "${REMOVE_DOMAIN_ONLY}" == "1" ]]; then
  log "REMOVE_DOMAIN_ONLY=1; done."
  exit 0
fi

if [[ "${DESTROY_DB}" == "1" ]]; then
  destroy_postgres_addons_if_present
else
  log "DESTROY_DB!=1; keeping Postgres addon(s)"
fi

if [[ "${DESTROY_APP}" != "1" ]]; then
  log "DESTROY_APP!=1; app kept intact. Done."
  exit 0
fi

if [[ "${CONFIRM}" != "yes" ]]; then
  die "Refusing to destroy app without CONFIRM=yes"
fi

log "Destroying Heroku app ${STAGING_APP}"
heroku apps:destroy "${STAGING_APP}" --confirm "${STAGING_APP}"
log "Destroyed ${STAGING_APP}"
