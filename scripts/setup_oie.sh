#!/usr/bin/env bash
# setup_oie — bring up local Postgres for OpenCRE OIE (A→B→C) and sync the CRE hub.
#
# Reusable local bootstrap. Idempotent where possible.
#
#   ./scripts/setup_oie.sh --source local
#   ./scripts/setup_oie.sh --source upstream          # Heroku APP_NAME (default opencreorg)
#   ./scripts/setup_oie.sh --source local --calibrate # also fit CRE_LIBRARIAN_TEMPERATURE
#   ./scripts/setup_oie.sh --source local --install-ml
#
# Writes env knobs to tmp/oie.env (source before running the orchestrator).
#
# Env overrides:
#   PG_URL / DEV_DATABASE_URL   local Postgres URL
#   SQLITE_HUB                  path to standards_cache.sqlite
#   APP_NAME / HEROKU_APP       upstream Heroku app (default opencreorg)
#   OIE_ENV_FILE                output env file (default tmp/oie.env)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

DB_SCRIPT_NAME="setup_oie"
# shellcheck source=scripts/db/common.sh
source "${ROOT}/scripts/db/common.sh"

PG_URL="${PG_URL:-${DEV_DATABASE_URL:-postgresql://cre:password@127.0.0.1:5432/cre}}"
SQLITE_HUB="${SQLITE_HUB:-${ROOT}/standards_cache.sqlite}"
OIE_ENV_FILE="${OIE_ENV_FILE:-${ROOT}/tmp/oie.env}"
OIE_DIR="${ROOT}/tmp/oie_owasp_eval"
SOURCE="local"
DO_CALIBRATE=0
DO_INSTALL_ML=0
SKIP_DOCKER=0
SKIP_SYNC=0
FORCE_SYNC=0
MIN_CRE_EMB="${MIN_CRE_EMB:-400}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  cat <<EOF

Options:
  --source local|upstream   Hub source (default: local sqlite)
  --sqlite PATH             Local hub sqlite (default: ./standards_cache.sqlite)
  --pg-url URL              Local Postgres (default: ${PG_URL})
  --install-ml              pip install sentence-transformers (Module C.2)
  --calibrate               Fit CRE_LIBRARIAN_TEMPERATURE; write into env file
  --skip-docker             Assume cre-postgres already running
  --skip-sync               Skip hub sync (schema/migrate + env only)
  --force-sync              Sync even if local hub already looks populated
  -h, --help                This help
EOF
}

log() { echo "[setup_oie] $*"; }
die() { echo "[setup_oie] ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="${2:-}"; shift 2 ;;
    --sqlite) SQLITE_HUB="${2:-}"; shift 2 ;;
    --pg-url) PG_URL="${2:-}"; shift 2 ;;
    --install-ml) DO_INSTALL_ML=1; shift ;;
    --calibrate) DO_CALIBRATE=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --skip-sync) SKIP_SYNC=1; shift ;;
    --force-sync) FORCE_SYNC=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1 (try --help)" ;;
  esac
done

[[ "${SOURCE}" == "local" || "${SOURCE}" == "upstream" ]] || die "--source must be local|upstream"

ensure_venv() {
  if [[ -d "${ROOT}/venv" ]]; then
    # shellcheck disable=SC1091
    source "${ROOT}/venv/bin/activate"
  else
    die "venv missing — run make install-python first"
  fi
}

ensure_docker_postgres() {
  if [[ "${SKIP_DOCKER}" == "1" ]]; then
    log "skip-docker: not starting cre-postgres"
    return
  fi
  if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null 2>&1; then
      log "docker not ready — starting colima"
      colima start
    else
      die "docker is not running and colima is not installed"
    fi
  fi
  log "starting cre-postgres (make docker-postgres)"
  make docker-postgres
}

migrate_local() {
  log "flask db upgrade → ${PG_URL}"
  export FLASK_APP="${ROOT}/cre.py"
  export FLASK_CONFIG="${FLASK_CONFIG:-development}"
  export NO_LOAD_GRAPH_DB=1
  export DEV_DATABASE_URL="${PG_URL}"
  flask db upgrade
}

cre_emb_count() {
  psql "${PG_URL}" -Atc \
    "SELECT count(*) FROM embeddings WHERE doc_type = 'CRE' AND embedding_vec IS NOT NULL" \
    2>/dev/null || echo 0
}

sync_hub() {
  if [[ "${SKIP_SYNC}" == "1" ]]; then
    log "skip-sync"
    return
  fi
  local count
  count="$(cre_emb_count)"
  if [[ "${FORCE_SYNC}" != "1" && "${count}" -ge "${MIN_CRE_EMB}" ]]; then
    log "CRE hub already populated (${count} embeddings ≥ ${MIN_CRE_EMB}); skip sync (use --force-sync to refresh)"
    return
  fi

  ensure_venv
  mkdir -p "${OIE_DIR}"
  if [[ "${SOURCE}" == "local" ]]; then
    [[ -f "${SQLITE_HUB}" ]] || die "sqlite hub not found: ${SQLITE_HUB}"
    log "syncing CRE hub from local sqlite ${SQLITE_HUB}"
    PYTHONPATH="${ROOT}" python "${ROOT}/scripts/oie_sync_cre_hub.py" \
      --from-sqlite "${SQLITE_HUB}" \
      --to-postgres "${PG_URL}"
  else
    ensure_heroku_auth
    local up_url
    up_url="$(resolve_app_database_url)"
    log "syncing CRE hub from upstream Heroku app ${APP_NAME} (read-only)"
    PYTHONPATH="${ROOT}" python "${ROOT}/scripts/oie_sync_cre_hub.py" \
      --from-postgres "${up_url}" \
      --to-postgres "${PG_URL}"
  fi
}

install_ml() {
  [[ "${DO_INSTALL_ML}" == "1" ]] || return 0
  ensure_venv
  log "pip install sentence-transformers (C.2 cross-encoder; not on prod requirements.txt)"
  pip install 'sentence-transformers>=5,<6'
}

write_env_file() {
  local temperature="${1:-1.0}"
  mkdir -p "$(dirname "${OIE_ENV_FILE}")"
  cat >"${OIE_ENV_FILE}" <<EOF
# Generated by scripts/setup_oie.sh — source before OIE runs.
#   set -a && source ${OIE_ENV_FILE} && set +a

FLASK_CONFIG=development
NO_LOAD_GRAPH_DB=1
DEV_DATABASE_URL=${PG_URL}
CRE_CACHE_FILE=${PG_URL}

CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector
CRE_LIBRARIAN_LINK_THRESHOLD=0.8
CRE_LIBRARIAN_TEMPERATURE=${temperature}

# Optional: HF_TOKEN speeds CrossEncoder download / avoids Hub rate limits.
EOF
  log "wrote ${OIE_ENV_FILE} (T=${temperature})"
}

calibrate_temperature() {
  [[ "${DO_CALIBRATE}" == "1" ]] || {
    write_env_file "1.0"
    log "skipped calibrate — CRE_LIBRARIAN_TEMPERATURE=1.0 (uncalibrated). Re-run with --calibrate."
    return 0
  }
  ensure_venv
  if ! python -c "import sentence_transformers" 2>/dev/null; then
    die "sentence-transformers required for --calibrate (pass --install-ml)"
  fi
  # Load API keys from repo .env if present (do not overwrite existing exports).
  if [[ -f "${ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^(GEMINI_API_KEY|OPENAI_API_KEY|LLM_API_KEY|HF_TOKEN)=' "${ROOT}/.env" | sed 's/^/export /' || true)
    set +a
  fi
  [[ -n "${GEMINI_API_KEY:-}${OPENAI_API_KEY:-}${LLM_API_KEY:-}" ]] || \
    die "need GEMINI_API_KEY or OPENAI_API_KEY in env/.env for live calibration"

  export FLASK_CONFIG=development
  export NO_LOAD_GRAPH_DB=1
  export DEV_DATABASE_URL="${PG_URL}"
  export CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector
  export CRE_LIBRARIAN_LINK_THRESHOLD=0.8

  mkdir -p "${OIE_DIR}"
  local logf="${OIE_DIR}/evaluate_librarian_live.log"
  log "fitting CRE_LIBRARIAN_TEMPERATURE (live embeddings) — log: ${logf}"
  set +e
  PYTHONPATH="${ROOT}" python -u "${ROOT}/scripts/evaluate_librarian.py" \
    --dataset "${ROOT}/application/tests/librarian/fixtures/golden_dataset.json" \
    --use_live_embeddings \
    --cache_file "${PG_URL}" \
    2>&1 | tee "${logf}"
  local rc=${PIPESTATUS[0]}
  set -e

  local t
  t="$(rg -o 'fitted T=[0-9.]+' "${logf}" | tail -1 | sed 's/fitted T=//' || true)"
  if [[ -z "${t}" ]]; then
    write_env_file "1.0"
    die "calibration did not print fitted T=… (rc=${rc}); see ${logf}"
  fi
  write_env_file "${t}"
  # Also stash machine-readable
  printf '%s\n' "${t}" >"${OIE_DIR}/fitted_temperature.txt"
  log "fitted T=${t} (also ${OIE_DIR}/fitted_temperature.txt)"
  [[ "${rc}" -eq 0 ]] || log "WARNING: evaluate_librarian exited ${rc} — T still written; check ECE gate in log"
}

print_next_steps() {
  cat <<EOF

[setup_oie] ready

  source env:   set -a && source ${OIE_ENV_FILE} && set +a
  hub check:    psql "\${DEV_DATABASE_URL}" -c "SELECT count(*) FROM embeddings WHERE doc_type='CRE'"
  run A→B→C:    PYTHONPATH=. python scripts/oie_owasp_eval/run_official_orchestrator_local.py \\
                  --cache-file "\${DEV_DATABASE_URL}" --a-mode tarball --max-chunks 20
  or:           make oie-pipeline CACHE_FILE="\${DEV_DATABASE_URL}" OIE_ARGS='--no-sync-repos'

EOF
}

main() {
  mkdir -p "${OIE_DIR}"
  ensure_docker_postgres
  ensure_venv
  command -v psql >/dev/null 2>&1 || die "psql required"
  command -v flask >/dev/null 2>&1 || die "flask required (venv)"

  migrate_local
  sync_hub
  install_ml
  calibrate_temperature
  print_next_steps

  local n
  n="$(cre_emb_count)"
  log "done — CRE embeddings with vec: ${n}"
  [[ "${n}" -ge 1 ]] || die "CRE hub empty after setup"
}

main
