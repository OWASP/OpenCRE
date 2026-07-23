#! /bin/bash

export INSECURE_REQUESTS=1
export FLASK_CONFIG="production"
export FLASK_APP=`pwd`/cre.py
flask db upgrade heads
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
python /code/cre.py --upstream_sync
gunicorn cre:app -b :5000 --timeout 90
