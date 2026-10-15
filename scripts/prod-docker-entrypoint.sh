#! /bin/bash
set -euo pipefail

export INSECURE_REQUESTS=1
export FLASK_CONFIG="${FLASK_CONFIG:-production}"
export FLASK_APP="${FLASK_APP:-$(pwd)/cre.py}"

# JWT API-token signing secret: use API_TOKEN_JWT_SECRET from env, or mint once
# into API_TOKEN_JWT_SECRET_FILE (default /code/.secrets/api_token_jwt_secret).
python - <<'PY'
from application.utils.api_tokens.secret import ensure_api_token_jwt_secret

ensure_api_token_jwt_secret()
PY

flask db upgrade heads

if [ -f /code/standards_cache.sqlite ]; then
  python - <<'PY'
import sqlite3

db_path = "/code/standards_cache.sqlite"
conn = sqlite3.connect(db_path)
try:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in ("cre", "node"):
        if table not in tables:
            continue
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "document_metadata" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN document_metadata JSON")
    conn.commit()
finally:
    conn.close()
PY
fi

skip_sync="$(echo "${CRE_SKIP_UPSTREAM_SYNC:-0}" | tr '[:upper:]' '[:lower:]')"
if [ "$skip_sync" != "1" ] && [ "$skip_sync" != "true" ] && [ "$skip_sync" != "yes" ]; then
  CACHE="${DATABASE_URL:-${DEV_DATABASE_URL:-/code/standards_cache.sqlite}}"
  python /code/cre.py --upstream_sync --cache_file "$CACHE"
fi

bind="${GUNICORN_BIND:-:5000}"
exec gunicorn cre:app -b "$bind" --timeout 90
