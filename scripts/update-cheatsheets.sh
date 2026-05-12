#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${1:-$ROOT_DIR/standards_cache.sqlite}"
VENV_DIR="$ROOT_DIR/venv"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if ! python -c "import flask" >/dev/null 2>&1; then
  pip install -r "$ROOT_DIR/requirements.txt"
fi

CRE_NO_CALCULATE_GAP_ANALYSIS=1 \
CRE_NO_GEN_EMBEDDINGS=1 \
python "$ROOT_DIR/cre.py" --cheatsheets_in --cache_file "$DB_PATH"

python - "$DB_PATH" <<'PY'
import os
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
cur = conn.cursor()

github_prefix = "https://github.com/OWASP/CheatSheetSeries/tree/master/cheatsheets/"
official_prefix = "https://cheatsheetseries.owasp.org/cheatsheets/"

rows = cur.execute(
    """
    select id, link
    from node
    where name = 'OWASP Cheat Sheets'
      and link like ?
    """,
    (f"{github_prefix}%",),
).fetchall()

for node_id, link in rows:
    filename = os.path.basename(link)
    html_name = os.path.splitext(filename)[0] + ".html"
    cur.execute(
        "update node set link = ? where id = ?",
        (f"{official_prefix}{html_name}", node_id),
    )

conn.commit()
conn.close()
print(f"Normalized {len(rows)} OWASP Cheat Sheet links")
PY
