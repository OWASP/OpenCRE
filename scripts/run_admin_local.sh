#!/usr/bin/env bash
# run_admin_local — start Flask admin against Docker Postgres (no SQLite).
#
# If DEV_DATABASE_URL / PG_URL is unset or unreachable, starts cre-postgres
# via `make docker-postgres`, sets the URL, migrates, then runs Flask.
#
#   ./scripts/run_admin_local.sh
#   ./scripts/run_admin_local.sh --migrate-only
#   PG_URL=postgresql://cre:password@127.0.0.1:5432/cre ./scripts/run_admin_local.sh
#
# Env:
#   PG_URL / DEV_DATABASE_URL   Postgres URL (default: make docker-postgres URL)
#   PORT                        Flask port (default 5000)
#   SKIP_DOCKER=1               Do not start the container (fail if unreachable)
#   SKIP_MIGRATE=1              Skip flask db upgrade
#   SKIP_UPSTREAM_SYNC=1        Do not pull CRE graph when cre/node tables are empty
#   FORCE_UPSTREAM_SYNC=1       Always run cre.py --upstream_sync before Flask

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

# Keep in sync with application.utils.postgres_url.DEFAULT_LOCAL_POSTGRES_URL
DEFAULT_PG_URL="postgresql://cre:password@127.0.0.1:5432/cre"
PG_URL="${PG_URL:-${DEV_DATABASE_URL:-${DEFAULT_PG_URL}}}"
PORT="${PORT:-5000}"
SKIP_DOCKER="${SKIP_DOCKER:-0}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"
SKIP_UPSTREAM_SYNC="${SKIP_UPSTREAM_SYNC:-0}"
FORCE_UPSTREAM_SYNC="${FORCE_UPSTREAM_SYNC:-0}"
# Model-only tables (e.g. staged_change_set) until Alembic catches up.
ADMIN_LOCAL_CREATE_ALL="${ADMIN_LOCAL_CREATE_ALL:-1}"
MIGRATE_ONLY=0

log() { echo "[admin-local] $*"; }
die() { echo "[admin-local] ERROR: $*" >&2; exit 1; }

redact_url() { sed -E 's#(://[^:/@]+):[^@/]*@#\1:***@#' <<<"$1"; }

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --migrate-only) MIGRATE_ONLY=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --skip-migrate) SKIP_MIGRATE=1; shift ;;
    --skip-upstream-sync) SKIP_UPSTREAM_SYNC=1; shift ;;
    --force-upstream-sync) FORCE_UPSTREAM_SYNC=1; shift ;;
    --pg-url) PG_URL="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1 (try --help)" ;;
  esac
done

ensure_venv() {
  if [[ -d "${ROOT}/venv" ]]; then
    # shellcheck disable=SC1091
    source "${ROOT}/venv/bin/activate"
  else
    die "venv missing — run make install-python first"
  fi
}

pg_reachable() {
  local url="$1"
  ensure_venv
  PYTHONPATH="${ROOT}" python - "$url" <<'PY'
import sys
from sqlalchemy import create_engine, text
from application.utils.postgres_url import is_postgres_url, sqlalchemy_postgres_url

raw = sys.argv[1]
if not is_postgres_url(raw):
    sys.exit(1)
try:
    url = sqlalchemy_postgres_url(raw)
except ValueError:
    sys.exit(1)
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception:
    sys.exit(1)
finally:
    engine.dispose()
sys.exit(0)
PY
}

run_with_docker_group() {
  # Fresh shells may not have the docker group until re-login.
  if docker info >/dev/null 2>&1; then
    "$@"
  elif command -v sg >/dev/null 2>&1 && sg docker -c 'docker info' >/dev/null 2>&1; then
    sg docker -c "$*"
  else
    return 1
  fi
}

ensure_docker() {
  if run_with_docker_group docker info >/dev/null 2>&1; then
    return 0
  fi
  if command -v colima >/dev/null 2>&1; then
    log "docker not ready — starting colima"
    colima start
    return 0
  fi
  die "docker is not running (install/start Docker, or set a reachable DEV_DATABASE_URL)"
}

ensure_postgres() {
  if pg_reachable "${PG_URL}"; then
    log "Postgres reachable at $(redact_url "${PG_URL}")"
    return 0
  fi
  if [[ "${SKIP_DOCKER}" == "1" ]]; then
    die "Postgres unreachable at $(redact_url "${PG_URL}") and SKIP_DOCKER=1"
  fi
  if [[ "${PG_URL}" != "${DEFAULT_PG_URL}" ]]; then
    log "custom PG_URL unreachable — still trying make docker-postgres, then falling back to ${DEFAULT_PG_URL}"
  fi
  ensure_docker
  log "starting cre-postgres (make docker-postgres)"
  run_with_docker_group make docker-postgres || die "make docker-postgres failed"
  PG_URL="${DEFAULT_PG_URL}"
  if ! pg_reachable "${PG_URL}"; then
    die "cre-postgres started but $(redact_url "${PG_URL}") still unreachable"
  fi
  log "populated DEV_DATABASE_URL=$(redact_url "${PG_URL}")"
}

migrate() {
  [[ "${SKIP_MIGRATE}" == "1" ]] && return 0
  ensure_venv
  log "flask db upgrade → $(redact_url "${PG_URL}")"
  export FLASK_APP="${ROOT}/cre.py"
  export FLASK_CONFIG=development
  export NO_LOAD_GRAPH_DB=1
  export DEV_DATABASE_URL="${PG_URL}"
  # Empty DBs cannot infer pgvector dim from rows.
  export CRE_EMBED_EXPECTED_DIM="${CRE_EMBED_EXPECTED_DIM:-3072}"
  unset CRE_CACHE_FILE || true
  # Stacked feature branches can leave multiple Alembic heads.
  flask db upgrade heads
  if [[ "${ADMIN_LOCAL_CREATE_ALL}" == "1" ]]; then
    # Some tables (e.g. staged_change_set) are still model-only on this stack.
    # Set ADMIN_LOCAL_CREATE_ALL=0 to require migrations only.
    log "sqla.create_all (ADMIN_LOCAL_CREATE_ALL=1) for model-only tables"
    PYTHONPATH="${ROOT}" python - <<'PY'
from application import create_app, sqla

app = create_app(mode="development")
with app.app_context():
    sqla.create_all()
print("create_all ok")
PY
  else
    log "skipping create_all (ADMIN_LOCAL_CREATE_ALL=0)"
  fi
}

cre_graph_empty() {
  ensure_venv
  PYTHONPATH="${ROOT}" DEV_DATABASE_URL="${PG_URL}" python - <<'PY'
import os
from sqlalchemy import create_engine, text
from application.utils.postgres_url import sqlalchemy_postgres_url

url = sqlalchemy_postgres_url(os.environ["DEV_DATABASE_URL"])
engine = create_engine(url, pool_pre_ping=True)
cre_n = node_n = 0
try:
    with engine.connect() as conn:
        cre_n = conn.execute(text("SELECT COUNT(*) FROM cre")).scalar() or 0
        node_n = conn.execute(text("SELECT COUNT(*) FROM node")).scalar() or 0
except Exception:
    # Tables may not exist yet; treat as empty so upstream sync can populate.
    raise SystemExit(0)
finally:
    engine.dispose()
raise SystemExit(0 if (cre_n == 0 or node_n == 0) else 1)
PY
}

ensure_upstream_graph() {
  if [[ "${SKIP_UPSTREAM_SYNC}" == "1" ]]; then
    log "skipping upstream CRE sync (SKIP_UPSTREAM_SYNC=1)"
    return 0
  fi
  ensure_venv
  export FLASK_APP="${ROOT}/cre.py"
  export FLASK_CONFIG=development
  export DEV_DATABASE_URL="${PG_URL}"
  export CRE_EMBED_EXPECTED_DIM="${CRE_EMBED_EXPECTED_DIM:-3072}"
  unset CRE_CACHE_FILE || true
  if [[ "${FORCE_UPSTREAM_SYNC}" == "1" ]]; then
    log "FORCE_UPSTREAM_SYNC=1 — pulling CRE graph from opencre.org"
  elif cre_graph_empty; then
    log "CRE graph empty (cre/node) — pulling from opencre.org via --upstream_sync"
  else
    log "CRE graph already present — skip upstream sync"
    return 0
  fi
  # OIE/admin harvest fills harvest_input; explorer needs the CRE/standards graph.
  PYTHONPATH="${ROOT}" python cre.py --upstream_sync --cache_file "${PG_URL}"
  log "upstream CRE sync finished"
}

run_flask() {
  ensure_venv
  export FLASK_APP="${ROOT}/cre.py"
  export FLASK_CONFIG=development
  export DEV_DATABASE_URL="${PG_URL}"
  export CRE_EMBED_EXPECTED_DIM="${CRE_EMBED_EXPECTED_DIM:-3072}"
  # Never fall back to SQLite for this path.
  unset CRE_CACHE_FILE || true
  export NO_LOGIN="${NO_LOGIN:-1}"
  export CRE_ALLOW_IMPORT="${CRE_ALLOW_IMPORT:-1}"
  export CRE_ENABLE_LOGIN="${CRE_ENABLE_LOGIN:-1}"
  export CRE_ENABLE_MYOPENCRE="${CRE_ENABLE_MYOPENCRE:-1}"
  export INSECURE_REQUESTS="${INSECURE_REQUESTS:-1}"
  export OWASP_AGENT_ENABLED="${OWASP_AGENT_ENABLED:-1}"
  unset OWASP_AGENT_DB || true
  log "Flask http://127.0.0.1:${PORT}/admin  DEV_DATABASE_URL=$(redact_url "${PG_URL}")"
  exec flask run --host 127.0.0.1 --port "${PORT}"
}

ensure_postgres
migrate
ensure_upstream_graph
if [[ "${MIGRATE_ONLY}" == "1" ]]; then
  log "migrate-only done"
  exit 0
fi
run_flask
