#! /bin/bash
set -euo pipefail

export INSECURE_REQUESTS=1
export FLASK_CONFIG="${FLASK_CONFIG:-production}"
export FLASK_APP="${FLASK_APP:-$(pwd)/cre.py}"

flask db upgrade heads

if [ -f /code/standards_cache.sqlite ]; then
  python - <<'PY'
import sqlite3

db_path = "/code/standards_cache.sqlite"
conn = sqlite3.connect(db_path)
for table in ("cre", "node"):
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if "document_metadata" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN document_metadata JSON")
conn.commit()
conn.close()
PY
fi

skip_sync="$(echo "${CRE_SKIP_UPSTREAM_SYNC:-0}" | tr '[:upper:]' '[:lower:]')"
if [ "$skip_sync" != "1" ] && [ "$skip_sync" != "true" ] && [ "$skip_sync" != "yes" ]; then
  python /code/cre.py --upstream_sync
fi

bind="${GUNICORN_BIND:-:5000}"
exec gunicorn cre:app -b "$bind" --timeout 90
