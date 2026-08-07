#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/venv"
CACHE_FILE="${1:-$ROOT_DIR/standards_cache.sqlite}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${CACHE_FILE}.bak.${TIMESTAMP}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing Python runtime dependencies"
pip install -r "$ROOT_DIR/requirements.txt"

if [[ -f "$CACHE_FILE" ]]; then
  cp "$CACHE_FILE" "$BACKUP_FILE"
  echo "Backed up database to $BACKUP_FILE"
fi

export CRE_NO_CALCULATE_GAP_ANALYSIS=1
export CRE_NO_GEN_EMBEDDINGS=1

echo "Importing OWASP Cheat Sheet data into $CACHE_FILE"
python "$ROOT_DIR/cre.py" --cheatsheets_in --cache_file "$CACHE_FILE"

# Normalise GitHub links to official HTML links
python - "$CACHE_FILE" <<'PY'
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