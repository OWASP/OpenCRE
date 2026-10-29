#!/usr/bin/env bash
# Deploy a branch to staging (staging.opencre.org) from your laptop. The only supported way to deploy:
# it takes a lock, backs up the host-only state, refuses deploys that would drop code already on
# staging, and smoke-tests the result, so two people (or sessions) cannot overwrite each other.
#
# Usage:
#   scripts/staging_deploy.sh [--branch feat/ext-integration] [--dry-run] [--no-migrate] [--force]
#   scripts/staging_deploy.sh --rollback <image-tag>     # e.g. pre-deploy-20261029-2201
#   scripts/staging_deploy.sh --status                   # who holds the lock, what is deployed
#
# Env:
#   STAGING_HOST          ssh target                         (default sg@100.74.143.62)
#   STAGING_DIR           deploy/staging on the host         (default /home/sg/Projects/OpenCRE/deploy/staging)
#   STAGING_SMOKE_TOKEN   an API key / OAuth access token; enables the authenticated `ask` smoke check
#   STAGING_DEPLOY_WHO    label stored in the lock           (default $USER)
#
# What it does, in order (see docs/oie/staging-deploy.md):
#   1. lock          mkdir lock on the host; refuses if another deploy is running
#   2. guard         the new commit must contain the deployed commit (no silent downgrade) and the
#                    host-only features must still be wired (OAuth module, nginx routes, .env flags)
#   3. backup        .env, overlays/mcp, overlays/edge/nginx.conf, and the current image tag
#   4. build         git archive origin/<branch> -> host, docker build -f Dockerfile.hotpatch
#   5. overlays      application/mcp/*.py and application/utils/api_tokens/*.py copied into overlays;
#                    http_app.py is 3-way merged so the host-only SseFirstByteMiddleware patch survives
#   6. migrate       flask db upgrade in a one-off container with the tree's migrations mounted
#   7. switch        tag :latest, compose up --force-recreate web mcp edge
#   8. smoke         /, /register 201, /mcp 401, OAuth metadata, optional authenticated ask
# Never touched: .env values, overlays/edge/nginx.conf, the database contents.
set -euo pipefail

HOST="${STAGING_HOST:-sg@100.74.143.62}"
DIR="${STAGING_DIR:-/home/sg/Projects/OpenCRE/deploy/staging}"
BASE_URL="${STAGING_BASE_URL:-https://staging.opencre.org}"
WHO="${STAGING_DEPLOY_WHO:-${USER:-unknown}}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.mcp-override.yml"
STALE_LOCK_MINUTES=90

BRANCH="feat/ext-integration"
DRY_RUN=0
MIGRATE=1
FORCE=0
ROLLBACK_TAG=""
MODE="deploy"
LOCK_HELD=0

while [ $# -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-migrate) MIGRATE=0; shift ;;
    --force) FORCE=1; shift ;;
    --rollback) MODE="rollback"; ROLLBACK_TAG="${2:?--rollback needs an image tag}"; shift 2 ;;
    --status) MODE="status"; shift ;;
    -h | --help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ssh_() { ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 "$HOST" "$@"; }
# Run a script on the host with DIR/COMPOSE available. Reads the script from stdin.
remote() { ssh_ "DIR='$DIR' COMPOSE='$COMPOSE' bash -s"; }

release_lock() {
  if [ "$LOCK_HELD" = 1 ]; then
    ssh_ "rm -rf '$DIR/.deploy.lock'" || true
    LOCK_HELD=0
  fi
}
trap release_lock EXIT

show_status() {
  say "staging status"
  remote <<'EOF'
cd "$DIR"
echo "deployed commit : $(cat DEPLOYED_COMMIT 2>/dev/null || echo unknown)"
echo "last deploys    :"; tail -n 5 DEPLOY_LOG 2>/dev/null | sed 's/^/  /' || true
if [ -d .deploy.lock ]; then echo "LOCK HELD       : $(cat .deploy.lock/info 2>/dev/null)"; else echo "lock            : free"; fi
echo "running images  :"; $COMPOSE ps --format '{{.Service}} {{.Image}} {{.Status}}' | grep -E '^(web|mcp|edge) ' | sed 's/^/  /'
echo "rollback images :"; docker images --format '{{.Tag}}' opencre-staging-web | grep '^pre-' | head -6 | sed 's/^/  /'
EOF
}

acquire_lock() {
  say "lock"
  local info
  info="$WHO $(date -u +%FT%TZ) branch=$BRANCH"
  if ! ssh_ "mkdir '$DIR/.deploy.lock' 2>/dev/null && echo '$info' > '$DIR/.deploy.lock/info'"; then
    local held age
    held="$(ssh_ "cat '$DIR/.deploy.lock/info' 2>/dev/null" || true)"
    age="$(ssh_ "find '$DIR/.deploy.lock' -maxdepth 0 -mmin +$STALE_LOCK_MINUTES -print 2>/dev/null" || true)"
    if [ -n "$age" ] && [ "$FORCE" = 1 ]; then
      echo "breaking stale lock (> ${STALE_LOCK_MINUTES} min): $held"
      ssh_ "rm -rf '$DIR/.deploy.lock' && mkdir '$DIR/.deploy.lock' && echo '$info' > '$DIR/.deploy.lock/info'"
    else
      die "another deploy holds the lock: ${held:-unknown}. Wait, or if it is stale (> ${STALE_LOCK_MINUTES} min) re-run with --force."
    fi
  fi
  LOCK_HELD=1
  echo "locked: $info"
}

if [ "$MODE" = status ]; then show_status; exit 0; fi

if [ "$MODE" = rollback ]; then
  acquire_lock
  say "rollback to opencre-staging-web:$ROLLBACK_TAG"
  if [ "$DRY_RUN" = 1 ]; then echo "(dry run) would retag and recreate"; exit 0; fi
  remote <<EOF
set -euo pipefail
cd "\$DIR"
docker image inspect opencre-staging-web:$ROLLBACK_TAG >/dev/null
docker tag opencre-staging-web:$ROLLBACK_TAG opencre-staging-web:latest
\$COMPOSE up -d --no-build --force-recreate web mcp edge
echo "\$(date -u +%FT%TZ) $WHO rollback to $ROLLBACK_TAG" >> DEPLOY_LOG
EOF
  echo "rolled back. NOTE: DEPLOYED_COMMIT is unchanged; set it by hand if the rollback is permanent."
  exit 0
fi

# ---- deploy -------------------------------------------------------------------------------------
say "resolve $BRANCH"
git fetch -q origin "$BRANCH" || die "cannot fetch origin/$BRANCH"
COMMIT="$(git rev-parse "origin/$BRANCH")"
SHORT="$(git rev-parse --short=8 "origin/$BRANCH")"
echo "deploying origin/$BRANCH @ $SHORT"
git cat-file -e "$COMMIT:application/mcp/oauth.py" 2>/dev/null ||
  die "origin/$BRANCH has no application/mcp/oauth.py: deploying it would remove MCP Google sign-in"
git cat-file -e "$COMMIT:deploy/staging/Dockerfile.hotpatch" 2>/dev/null ||
  die "origin/$BRANCH has no deploy/staging/Dockerfile.hotpatch"

acquire_lock

say "guard: what is deployed now"
DEPLOYED="$(ssh_ "cat '$DIR/DEPLOYED_COMMIT' 2>/dev/null" || true)"
echo "deployed commit: ${DEPLOYED:-unknown}"
if [ -n "$DEPLOYED" ] && git cat-file -e "$DEPLOYED^{commit}" 2>/dev/null; then
  if ! git merge-base --is-ancestor "$DEPLOYED" "$COMMIT"; then
    if [ "$FORCE" = 1 ]; then
      echo "WARNING: $SHORT does not contain deployed commit ${DEPLOYED:0:8}; --force given, continuing"
    else
      die "origin/$BRANCH @ $SHORT does not contain the deployed commit ${DEPLOYED:0:8}. Deploying it would drop code that is live on staging. Merge the deployed commit into the branch first (or --force)."
    fi
  fi
else
  echo "WARNING: deployed commit unknown to this clone; skipping the ancestry check"
fi

say "guard: host-only state"
remote <<'EOF' || die "host-only state check failed (see above)"
set -e
cd "$DIR"
fail=0
grep -q 'oauth' overlays/edge/nginx.conf || { echo "nginx.conf has no OAuth location block"; fail=1; }
grep -q 'SseFirstByteMiddleware' overlays/mcp/http_app.py || { echo "overlays/mcp/http_app.py lost the SSE patch"; fail=1; }
for k in OPENCRE_MCP_OAUTH OPENCRE_MCP_ALLOWED_DOMAINS OPENCRE_MCP_PUBLIC_URL GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
  grep -q "^$k=" .env || { echo ".env is missing $k"; fail=1; }
done
exit $fail
EOF

TS="$(date -u +%Y%m%d-%H%M%S)"
if [ "$DRY_RUN" = 1 ]; then
  say "dry run: stopping before any change on the host (lock released on exit)"
  echo "would: back up -> build $SHORT -> refresh overlays -> migrate=$MIGRATE -> switch -> smoke"
  exit 0
fi

say "backup (pre-deploy-$TS)"
remote <<EOF
set -euo pipefail
cd "\$DIR"
mkdir -p backups/pre-deploy-$TS
cp -a .env overlays/mcp overlays/edge/nginx.conf backups/pre-deploy-$TS/
[ -d overlays/api_tokens ] && cp -a overlays/api_tokens backups/pre-deploy-$TS/ || true
docker tag opencre-staging-web:latest opencre-staging-web:pre-deploy-$TS
echo "backed up to backups/pre-deploy-$TS, image tagged pre-deploy-$TS"
EOF

say "build"
SRC="/home/sg/staging-src/$SHORT"
ssh_ "rm -rf '$SRC' && mkdir -p '$SRC'"
git archive "$COMMIT" | ssh_ "tar -x -C '$SRC'"
ssh_ "echo $COMMIT > '$SRC/.deployed-commit' && cd '$SRC' && docker build -q -f deploy/staging/Dockerfile.hotpatch -t opencre-staging-web:$SHORT . >/dev/null && echo built opencre-staging-web:$SHORT"

say "overlays"
# http_app.py: host copy carries a staging-only patch, so merge instead of overwrite.
BASE_FILE="$(mktemp)"; HOST_FILE="$(mktemp)"; NEW_FILE="$(mktemp)"
scp -q -o BatchMode=yes "$HOST:$DIR/overlays/mcp/http_app.py" "$HOST_FILE"
git show "$COMMIT:application/mcp/http_app.py" > "$NEW_FILE"
if [ -n "$DEPLOYED" ] && git cat-file -e "$DEPLOYED:application/mcp/http_app.py" 2>/dev/null; then
  git show "$DEPLOYED:application/mcp/http_app.py" > "$BASE_FILE"
  cp "$HOST_FILE" "$HOST_FILE.merged"
  if ! git merge-file -p "$HOST_FILE" "$BASE_FILE" "$NEW_FILE" > "$HOST_FILE.merged"; then
    die "http_app.py does not merge cleanly with the host copy (SSE patch). Nothing was switched; resolve by hand in $DIR/overlays/mcp/http_app.py"
  fi
else
  # No base to merge against: only safe when the host copy already equals the new tree.
  cmp -s "$HOST_FILE" "$NEW_FILE" && cp "$HOST_FILE" "$HOST_FILE.merged" ||
    die "no deployed commit to merge http_app.py against and the host copy differs from the tree"
fi
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$HOST_FILE.merged" || die "merged http_app.py is not valid Python"
grep -q SseFirstByteMiddleware "$HOST_FILE.merged" || die "merged http_app.py lost the SSE patch"
scp -q -o BatchMode=yes "$HOST_FILE.merged" "$HOST:$DIR/overlays/mcp/http_app.py"
rm -f "$BASE_FILE" "$HOST_FILE" "$NEW_FILE" "$HOST_FILE.merged"
remote <<EOF
set -euo pipefail
cd "\$DIR"
for f in $SRC/application/mcp/*.py; do b=\$(basename "\$f"); [ "\$b" = http_app.py ] && continue; cp "\$f" "overlays/mcp/\$b"; done
if [ -d overlays/api_tokens ]; then cp $SRC/application/utils/api_tokens/*.py overlays/api_tokens/; fi
[ -f $SRC/docs/api/mcp.md ] && cp $SRC/docs/api/mcp.md overlays/docs_api/mcp.md || true
echo "overlays refreshed"
EOF

if [ "$MIGRATE" = 1 ]; then
  say "migrate"
  remote <<EOF
set -euo pipefail
cd "\$DIR"
\$COMPOSE run --rm --no-deps -v $SRC/migrations:/code/migrations:ro --entrypoint bash web -lc \
  'cd /code && export FLASK_APP=/code/cre.py FLASK_CONFIG=production INSECURE_REQUESTS=1 && flask db upgrade head 2>&1 | grep -vE "^\{" | tail -5'
EOF
fi

say "switch"
remote <<EOF
set -euo pipefail
cd "\$DIR"
docker tag opencre-staging-web:$SHORT opencre-staging-web:latest
\$COMPOSE up -d --no-build --force-recreate web mcp edge 2>&1 | tail -3
EOF

say "smoke"
FAILED=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then echo "ok    $1 ($3)"; else echo "FAIL  $1: expected $2, got $3"; FAILED=1; fi
}
for _ in $(seq 1 24); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$BASE_URL/" || true)" = 200 ] && break
  sleep 5
done
check "home" 200 "$(curl -s -o /dev/null -w '%{http_code}' -m 15 "$BASE_URL/" || true)"
check "oauth metadata" 200 "$(curl -s -o /dev/null -w '%{http_code}' -m 15 "$BASE_URL/.well-known/oauth-authorization-server" || true)"
check "/mcp without token" 401 "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$BASE_URL/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{}' || true)"
check "/register" 201 "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$BASE_URL/register" -H 'Content-Type: application/json' \
  -d '{"redirect_uris":["http://localhost:9/cb"],"token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"],"response_types":["code"],"client_name":"staging-deploy-smoke"}' || true)"
remote <<'EOF' >/dev/null 2>&1 || true
cd "$DIR"
$COMPOSE exec -T db psql -U cre -d cre -Atc "delete from mcp_oauth_clients where info_json like '%staging-deploy-smoke%';"
EOF
if [ -n "${STAGING_SMOKE_TOKEN:-}" ]; then
  RESULT="$(STAGING_SMOKE_TOKEN="$STAGING_SMOKE_TOKEN" BASE_URL="$BASE_URL" python3 - <<'PY' || true
import json, os, urllib.request
base, tok = os.environ["BASE_URL"], os.environ["STAGING_SMOKE_TOKEN"]
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Authorization": "Bearer " + tok}
def post(body, sid=None):
    h = dict(H)
    if sid: h["mcp-session-id"] = sid
    req = urllib.request.Request(base + "/mcp", json.dumps(body).encode(), h)
    return urllib.request.urlopen(req, timeout=120)
r = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "deploy-smoke", "version": "1"}}})
sid = r.headers["mcp-session-id"]
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
d = json.load(post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ask", "arguments": {"prompt": "What does ASVS require for password storage?"}}}, sid))
print("error" if d["result"].get("isError") else "ok")
PY
)"
  check "authenticated ask" ok "${RESULT:-none}"
else
  echo "skip  authenticated ask (set STAGING_SMOKE_TOKEN to enable)"
fi

if [ "$FAILED" != 0 ]; then
  die "smoke checks failed. Roll back with: scripts/staging_deploy.sh --rollback pre-deploy-$TS"
fi
remote <<EOF
set -euo pipefail
cd "\$DIR"
echo $COMMIT > DEPLOYED_COMMIT
echo "\$(date -u +%FT%TZ) $WHO deployed $BRANCH @ $SHORT (rollback image pre-deploy-$TS)" >> DEPLOY_LOG
EOF
say "done: staging runs origin/$BRANCH @ $SHORT. Rollback image: pre-deploy-$TS"
