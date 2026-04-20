#!/usr/bin/env bash

set -euo pipefail

log() {
  echo "[setup-heroku-staging] $*"
}

die() {
  echo "[setup-heroku-staging] ERROR: $*" >&2
  exit 1
}

# Required:
#   PROD_APP                e.g. opencreorg
#   STAGING_APP             e.g. opencre-staging
#   LOCAL_SQLITE_DB         e.g. /home/sg/Projects/OpenCRE/standards_cache.sqlite
#
# Optional:
#   SOURCE_REF              git ref to deploy to Heroku (default: HEAD)
#   HEROKU_TEAM             Heroku team/enterprise org to own app
#   HEROKU_REGION           us|eu (default: us)
#   POSTGRES_PLAN           addon plan (default: heroku-postgresql:standard-0)
#   STAGING_DOMAIN          custom domain (default: staging.opencre.org)
#   IMPORT_WITH_DOCKER      1 to use Docker pgloader if local pgloader missing (default: 1)
#   PGLOADER_NO_SSL_VERIFY  1 to pass --no-ssl-cert-verification (default: 1)
#   IMPORT_METHOD           direct_pgloader|local_postgres_push (default: local_postgres_push)
#   LOCAL_PG_URL            optional when IMPORT_METHOD=local_postgres_push.
#                           e.g. postgres://postgres:postgres@127.0.0.1:5432/opencre_staging_seed
#   AUTO_LOCAL_PG_DOCKER    1 to auto-start local postgres docker when LOCAL_PG_URL is empty (default: 1)
#   LOCAL_PG_CONTAINER      local postgres container name (default: opencre-local-pg-staging)
#   LOCAL_PG_PORT           host port for local postgres docker (default: 55432)
#   LOCAL_PG_DB             local postgres db name (default: opencre_staging_seed)
#   LOCAL_PG_USER           local postgres user (default: postgres)
#   LOCAL_PG_PASSWORD       local postgres password (default: postgres)
#   ENABLE_HEROKU_ACM       1 to auto-enable Heroku ACM cert management (default: 1)
#   SYNC_DYNO_FORMATION     1 to mirror prod dyno size+count on staging (default: 1)
#   SKIP_DEPLOY             1 to skip git push to Heroku
#   STRICT_ENV_SYNC         1 to unset staging vars not in prod (excluding protected keys)
#   SYNC_TABLES             all|embeddings|gap_analysis|embeddings,gap_analysis (default: all)
#
# CLI flags (override SYNC_TABLES):
#   --embeddings
#   --gap_analysis
#   --delete                  run teardown flow instead of bootstrap flow

PROD_APP="${PROD_APP:-}"
STAGING_APP="${STAGING_APP:-}"
LOCAL_SQLITE_DB="${LOCAL_SQLITE_DB:-}"
SOURCE_REF="${SOURCE_REF:-HEAD}"
HEROKU_TEAM="${HEROKU_TEAM:-}"
HEROKU_REGION="${HEROKU_REGION:-us}"
POSTGRES_PLAN="${POSTGRES_PLAN:-heroku-postgresql:standard-0}"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.opencre.org}"
IMPORT_WITH_DOCKER="${IMPORT_WITH_DOCKER:-1}"
PGLOADER_NO_SSL_VERIFY="${PGLOADER_NO_SSL_VERIFY:-1}"
IMPORT_METHOD="${IMPORT_METHOD:-local_postgres_push}"
LOCAL_PG_URL="${LOCAL_PG_URL:-}"
AUTO_LOCAL_PG_DOCKER="${AUTO_LOCAL_PG_DOCKER:-1}"
LOCAL_PG_CONTAINER="${LOCAL_PG_CONTAINER:-opencre-local-pg-staging}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-55432}"
LOCAL_PG_DB="${LOCAL_PG_DB:-opencre_staging_seed}"
LOCAL_PG_USER="${LOCAL_PG_USER:-postgres}"
LOCAL_PG_PASSWORD="${LOCAL_PG_PASSWORD:-postgres}"
ENABLE_HEROKU_ACM="${ENABLE_HEROKU_ACM:-1}"
SYNC_DYNO_FORMATION="${SYNC_DYNO_FORMATION:-1}"
SKIP_DEPLOY="${SKIP_DEPLOY:-0}"
STRICT_ENV_SYNC="${STRICT_ENV_SYNC:-0}"
SYNC_TABLES="${SYNC_TABLES:-all}"

SYNC_EMBEDDINGS=0
SYNC_GAP_ANALYSIS=0
DELETE_MODE=0
for arg in "$@"; do
  case "${arg}" in
    --embeddings)
      SYNC_EMBEDDINGS=1
      ;;
    --gap_analysis)
      SYNC_GAP_ANALYSIS=1
      ;;
    --delete)
      DELETE_MODE=1
      ;;
    *)
      die "Unknown argument: ${arg} (supported: --embeddings, --gap_analysis, --delete)"
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

[[ -n "${STAGING_APP}" ]] || die "STAGING_APP is required"
if [[ "${DELETE_MODE}" != "1" ]]; then
  [[ -n "${PROD_APP}" ]] || die "PROD_APP is required"
  [[ -n "${LOCAL_SQLITE_DB}" ]] || die "LOCAL_SQLITE_DB is required"
  [[ -f "${LOCAL_SQLITE_DB}" ]] || die "LOCAL_SQLITE_DB does not exist: ${LOCAL_SQLITE_DB}"
fi

command -v heroku >/dev/null 2>&1 || die "heroku CLI not found"
command -v git >/dev/null 2>&1 || die "git not found"

if ! heroku auth:whoami >/dev/null 2>&1; then
  die "Not logged in to Heroku. Run: heroku login"
fi

if [[ "${IMPORT_METHOD}" != "direct_pgloader" && "${IMPORT_METHOD}" != "local_postgres_push" ]]; then
  die "IMPORT_METHOD must be one of: direct_pgloader, local_postgres_push"
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
prod_env_file="${tmpdir}/prod.env"
staging_env_file="${tmpdir}/staging.env"
sync_env_file="${tmpdir}/sync.env"

app_exists() {
  heroku apps:info -a "$1" >/dev/null 2>&1
}

ensure_app() {
  if app_exists "${STAGING_APP}"; then
    log "Heroku app exists: ${STAGING_APP}"
    return
  fi
  log "Creating Heroku app: ${STAGING_APP}"
  if [[ -n "${HEROKU_TEAM}" ]]; then
    heroku apps:create "${STAGING_APP}" --team "${HEROKU_TEAM}" --region "${HEROKU_REGION}"
  else
    heroku apps:create "${STAGING_APP}" --region "${HEROKU_REGION}"
  fi
}

ensure_postgres() {
  if heroku addons -a "${STAGING_APP}" | grep -q "heroku-postgresql"; then
    log "Postgres addon already present on ${STAGING_APP}"
  else
    log "Provisioning Postgres (${POSTGRES_PLAN}) on ${STAGING_APP}"
    heroku addons:create "${POSTGRES_PLAN}" -a "${STAGING_APP}"
  fi
}

sync_dyno_formation_from_prod() {
  if [[ "${SYNC_DYNO_FORMATION}" != "1" ]]; then
    log "SYNC_DYNO_FORMATION!=1; skipping dyno size/count sync"
    return
  fi

  local prod_ps_json
  prod_ps_json="$(heroku ps -a "${PROD_APP}" --json)"
  if [[ -z "${prod_ps_json}" || "${prod_ps_json}" == "[]" ]]; then
    log "No running dynos detected on ${PROD_APP}; skipping dyno sync"
    return
  fi

  local formation_lines
  formation_lines="$(python3 - <<'PY' "${prod_ps_json}"
import json
import sys
from collections import defaultdict

rows = json.loads(sys.argv[1])
sizes = {}
counts = defaultdict(int)
for row in rows:
    typ = row.get("type")
    size = row.get("size")
    if not typ or not size:
        continue
    counts[typ] += 1
    sizes[typ] = size

for typ in sorted(counts.keys()):
    print(f"{typ}|{sizes[typ]}|{counts[typ]}")
PY
)"

  if [[ -z "${formation_lines}" ]]; then
    log "Could not derive formation from ${PROD_APP}; skipping dyno sync"
    return
  fi

  while IFS='|' read -r process_type process_size process_qty; do
    [[ -n "${process_type}" ]] || continue
    local size_norm
    size_norm="$(echo "${process_size}" | tr '[:upper:]' '[:lower:]')"
    log "Setting staging dyno type ${process_type} to size ${size_norm}"
    heroku ps:type -a "${STAGING_APP}" "${process_type}=${size_norm}" >/dev/null
    log "Scaling staging dyno type ${process_type} to ${process_qty}"
    heroku ps:scale -a "${STAGING_APP}" "${process_type}=${process_qty}" >/dev/null
  done <<< "${formation_lines}"
}

ensure_local_postgres_if_needed() {
  if [[ "${IMPORT_METHOD}" != "local_postgres_push" || -n "${LOCAL_PG_URL}" ]]; then
    return
  fi
  if [[ "${AUTO_LOCAL_PG_DOCKER}" != "1" ]]; then
    die "LOCAL_PG_URL is empty and AUTO_LOCAL_PG_DOCKER!=1"
  fi
  command -v docker >/dev/null 2>&1 || die "docker required for AUTO_LOCAL_PG_DOCKER=1"

  LOCAL_PG_URL="postgres://${LOCAL_PG_USER}:${LOCAL_PG_PASSWORD}@127.0.0.1:${LOCAL_PG_PORT}/${LOCAL_PG_DB}"
  log "LOCAL_PG_URL not set; using dockerized local Postgres at ${LOCAL_PG_URL}"

  if docker ps -a --format '{{.Names}}' | grep -q "^${LOCAL_PG_CONTAINER}$"; then
    docker start "${LOCAL_PG_CONTAINER}" >/dev/null
  else
    docker run -d --name "${LOCAL_PG_CONTAINER}" \
      -e POSTGRES_PASSWORD="${LOCAL_PG_PASSWORD}" \
      -e POSTGRES_USER="${LOCAL_PG_USER}" \
      -e POSTGRES_DB="${LOCAL_PG_DB}" \
      -p "${LOCAL_PG_PORT}:5432" \
      postgres:16 >/dev/null
  fi

  local ready=0
  for _ in $(seq 1 30); do
    if docker exec "${LOCAL_PG_CONTAINER}" pg_isready -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  [[ "${ready}" == "1" ]] || die "Local postgres docker did not become ready in time"
}

copy_env_from_prod() {
  log "Fetching config vars from ${PROD_APP}"
  heroku config -s -a "${PROD_APP}" > "${prod_env_file}"
  heroku config -s -a "${STAGING_APP}" > "${staging_env_file}"

  # Remove DB and Heroku-managed/runtime-specific keys.
  grep -Ev '^(DATABASE_URL|PROD_DATABASE_URL|HEROKU_|DYNO=|PORT=|STACK=|APP_NAME=)' "${prod_env_file}" > "${sync_env_file}" || true

  if [[ -s "${sync_env_file}" ]]; then
    log "Applying production env vars to ${STAGING_APP} (excluding DATABASE_URL and managed keys)"
    heroku config:set -a "${STAGING_APP}" $(tr '\n' ' ' < "${sync_env_file}") >/dev/null
  else
    log "No copyable config vars found from ${PROD_APP}"
  fi

  if [[ "${STRICT_ENV_SYNC}" == "1" ]]; then
    log "STRICT_ENV_SYNC=1; unsetting extra vars present only on staging"
    while IFS='=' read -r key _; do
      [[ -n "${key}" ]] || continue
      if [[ "${key}" =~ ^(DATABASE_URL|PROD_DATABASE_URL|HEROKU_|DYNO|PORT|STACK|APP_NAME)$ ]]; then
        continue
      fi
      if ! grep -q "^${key}=" "${prod_env_file}"; then
        heroku config:unset "${key}" -a "${STAGING_APP}" >/dev/null
      fi
    done < "${staging_env_file}"
  fi
}

sync_prod_database_url_to_staging_db() {
  local staging_db_url
  local sqlalchemy_db_url
  staging_db_url="$(heroku config:get DATABASE_URL -a "${STAGING_APP}")"
  [[ -n "${staging_db_url}" ]] || die "Failed to resolve staging DATABASE_URL"
  sqlalchemy_db_url="${staging_db_url}"
  # SQLAlchemy expects postgresql:// (not postgres://) on newer stacks.
  sqlalchemy_db_url="${sqlalchemy_db_url/#postgres:\/\//postgresql://}"
  log "Setting PROD_DATABASE_URL to staging DATABASE_URL (SQLAlchemy-safe scheme)"
  heroku config:set -a "${STAGING_APP}" "PROD_DATABASE_URL=${sqlalchemy_db_url}" >/dev/null
}

deploy_source() {
  if [[ "${SKIP_DEPLOY}" == "1" ]]; then
    log "SKIP_DEPLOY=1; skipping code deploy"
    return
  fi
  log "Deploying ${SOURCE_REF} to Heroku app ${STAGING_APP}"
  if git remote | grep -q '^heroku-staging$'; then
    git remote set-url heroku-staging "https://git.heroku.com/${STAGING_APP}.git"
  else
    git remote add heroku-staging "https://git.heroku.com/${STAGING_APP}.git"
  fi
  git push heroku-staging "${SOURCE_REF}":main --force
}

run_pgloader() {
  local sqlite_db="$1"
  local pg_url="$2"
  local pg_url_ssl="$2"
  local -a pgloader_args=()

  # Heroku Postgres requires SSL for external clients.
  if [[ "${pg_url_ssl}" == *"sslmode="* ]]; then
    :
  elif [[ "${pg_url_ssl}" == *"?"* ]]; then
    pg_url_ssl="${pg_url_ssl}&sslmode=require"
  else
    pg_url_ssl="${pg_url_ssl}?sslmode=require"
  fi

  # Heroku Postgres + pgloader commonly needs SSL verification disabled
  # in CI/container contexts due to cert chain handling in pgloader OpenSSL.
  if [[ "${PGLOADER_NO_SSL_VERIFY}" == "1" ]]; then
    pgloader_args+=(--no-ssl-cert-verification)
  fi

  if command -v pgloader >/dev/null 2>&1; then
    log "Importing sqlite into Heroku Postgres using local pgloader (sslmode=require)"
    pgloader "${pgloader_args[@]}" "sqlite://${sqlite_db}" "${pg_url_ssl}"
    return
  fi

  if [[ "${IMPORT_WITH_DOCKER}" != "1" ]]; then
    die "pgloader not found and IMPORT_WITH_DOCKER!=1"
  fi
  command -v docker >/dev/null 2>&1 || die "docker required for pgloader fallback"

  log "Importing sqlite into Heroku Postgres using Docker pgloader (sslmode=require)"
  docker run --rm \
    -v "${sqlite_db}:/tmp/standards_cache.sqlite:ro" \
    dimitri/pgloader:latest \
    pgloader "${pgloader_args[@]}" "sqlite:///tmp/standards_cache.sqlite" "${pg_url_ssl}"
}

import_sqlite_to_staging_postgres() {
  local staging_db_url
  local staging_db_url_ssl
  local pgloader_log
  local rc
  local source_url
  local dump_file
  staging_db_url="$(heroku config:get DATABASE_URL -a "${STAGING_APP}")"
  [[ -n "${staging_db_url}" ]] || die "Failed to resolve DATABASE_URL for ${STAGING_APP}"

  if [[ "${IMPORT_METHOD}" == "direct_pgloader" ]]; then
    run_pgloader "${LOCAL_SQLITE_DB}" "${staging_db_url}"
    return
  fi

  # Preferred path for Heroku: sqlite -> local postgres, then heroku pg:push.
  command -v pgloader >/dev/null 2>&1 || die "pgloader is required for IMPORT_METHOD=local_postgres_push"
  command -v psql >/dev/null 2>&1 || die "psql is required for IMPORT_METHOD=local_postgres_push"

  log "Importing sqlite into local Postgres: ${LOCAL_PG_URL}"
  # Rebuild local seed DB schema/content from sqlite.
  # pgloader can fail creating a FK on reserved identifier `group` in `cre_links`
  # after data COPY succeeded; we treat that specific failure as non-fatal.
  pgloader_log="${tmpdir}/pgloader-local.log"
  set +e
  pgloader "sqlite://${LOCAL_SQLITE_DB}" "${LOCAL_PG_URL}" >"${pgloader_log}" 2>&1
  rc=$?
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    if grep -q 'ALTER TABLE cre_links ADD FOREIGN KEY(group)' "${pgloader_log}"; then
      log "pgloader reported known FK issue on cre_links.group; continuing with imported data"
    else
      cat "${pgloader_log}" >&2
      die "pgloader local import failed"
    fi
  fi

  log "Pushing local Postgres into Heroku app ${STAGING_APP} DATABASE_URL"
  # Use pg_dump + pg_restore directly to avoid heroku pg:push SSL negotiation quirks.
  command -v pg_dump >/dev/null 2>&1 || die "pg_dump is required for local_postgres_push"
  command -v pg_restore >/dev/null 2>&1 || die "pg_restore is required for local_postgres_push"

  source_url="${LOCAL_PG_URL}"
  if [[ "${source_url}" == *"sslmode="* ]]; then
    :
  elif [[ "${source_url}" == *"?"* ]]; then
    source_url="${source_url}&sslmode=disable"
  else
    source_url="${source_url}?sslmode=disable"
  fi

  staging_db_url_ssl="${staging_db_url}"
  if [[ "${staging_db_url_ssl}" == *"sslmode="* ]]; then
    :
  elif [[ "${staging_db_url_ssl}" == *"?"* ]]; then
    staging_db_url_ssl="${staging_db_url_ssl}&sslmode=require"
  else
    staging_db_url_ssl="${staging_db_url_ssl}?sslmode=require"
  fi

  dump_file="${tmpdir}/local_staging_seed.dump"
  dump_cmd=(pg_dump --format=custom --no-owner --no-privileges --file "${dump_file}")
  if [[ "${SCOPE_ALL}" != "1" ]]; then
    if [[ "${SYNC_EMBEDDINGS}" == "1" ]]; then
      dump_cmd+=(--table public.embeddings)
    fi
    if [[ "${SYNC_GAP_ANALYSIS}" == "1" ]]; then
      dump_cmd+=(--table public.gap_analysis_results)
    fi
  fi
  dump_cmd+=("${source_url}")
  "${dump_cmd[@]}"

  restore_cmd=(pg_restore --no-owner --no-privileges --dbname "${staging_db_url_ssl}")
  if [[ "${SCOPE_ALL}" == "1" ]]; then
    restore_cmd=(pg_restore --clean --if-exists --no-owner --no-privileges --dbname "${staging_db_url_ssl}")
  else
    restore_cmd+=(--clean --if-exists)
  fi
  restore_cmd+=("${dump_file}")
  "${restore_cmd[@]}"
}

ensure_domain() {
  if heroku domains -a "${STAGING_APP}" | grep -qE "(^|[[:space:]])${STAGING_DOMAIN}([[:space:]]|$)"; then
    log "Custom domain already attached: ${STAGING_DOMAIN}"
  else
    log "Attaching custom domain ${STAGING_DOMAIN}"
    heroku domains:add "${STAGING_DOMAIN}" -a "${STAGING_APP}"
  fi
  log "Current domain targets:"
  heroku domains -a "${STAGING_APP}"
}

ensure_heroku_acm() {
  if [[ "${ENABLE_HEROKU_ACM}" != "1" ]]; then
    log "ENABLE_HEROKU_ACM!=1; skipping Heroku ACM setup"
    return
  fi

  log "Enabling Heroku ACM for automatic SSL cert provisioning"
  # Safe to run repeatedly; it is a no-op when ACM is already enabled.
  heroku certs:auto:enable -a "${STAGING_APP}" >/dev/null 2>&1 || true

  log "Heroku ACM status:"
  heroku certs:auto -a "${STAGING_APP}" || true
}

delete_staging_resources() {
  local script_dir teardown_script
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  teardown_script="${script_dir}/teardown-heroku-staging.sh"
  [[ -f "${teardown_script}" ]] || die "teardown script not found: ${teardown_script}"

  log "Delete mode enabled; delegating to teardown script"
  STAGING_APP="${STAGING_APP}" \
  STAGING_DOMAIN="${STAGING_DOMAIN}" \
  DESTROY_DB="${DESTROY_DB:-1}" \
  DESTROY_APP="${DESTROY_APP:-0}" \
  REMOVE_DOMAIN_ONLY="${REMOVE_DOMAIN_ONLY:-0}" \
  CONFIRM="${CONFIRM:-}" \
  bash "${teardown_script}"
}

main() {
  if [[ "${DELETE_MODE}" == "1" ]]; then
    delete_staging_resources
    return
  fi
  if [[ "${SCOPE_ALL}" == "1" ]]; then
    log "Sync scope: all tables"
  else
    log "Sync scope: ${SYNC_TABLES}"
  fi
  ensure_local_postgres_if_needed
  ensure_app
  ensure_postgres
  sync_dyno_formation_from_prod
  copy_env_from_prod
  sync_prod_database_url_to_staging_db
  deploy_source
  import_sqlite_to_staging_postgres
  ensure_domain
  ensure_heroku_acm

  log "Done."
  log "Verify app: https://${STAGING_DOMAIN}"
  log "If DNS is not configured yet, copy the DNS target from 'heroku domains' output."
}

main "$@"
