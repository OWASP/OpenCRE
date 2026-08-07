#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/venv"
CACHE_FILE="${1:-$ROOT_DIR/standards_cache.sqlite}"
REQ_FILE="$ROOT_DIR/requirements.txt"
STAMP_FILE="$VENV_DIR/.requirements.stamp"

# Ensure virtual environment exists
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Install requirements only if they have changed (optional optimisation)
if [[ ! -f "$STAMP_FILE" ]] || [[ "$REQ_FILE" -nt "$STAMP_FILE" ]]; then
  echo "Installing Python runtime dependencies"
  pip install -r "$REQ_FILE"
  touch "$STAMP_FILE"
else
  echo "Requirements up to date, skipping pip install"
fi

if [[ ! -f "$CACHE_FILE" ]]; then
  echo "Database file does not exist: $CACHE_FILE" >&2
  exit 1
fi

# Create a timestamped backup with PID to avoid collisions
BACKUP_FILE="${CACHE_FILE}.$(date +%Y%m%d%H%M%S)_$$.bak"

# Online backup + integrity check (safe for live DB, handles WAL)
python -c "
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
try:
    with sqlite3.connect(src) as src_conn:
        with sqlite3.connect(dst) as dst_conn:
            src_conn.backup(dst_conn)
            cur = dst_conn.cursor()
            cur.execute('PRAGMA integrity_check')
            if cur.fetchone()[0] != 'ok':
                print('Integrity check failed for backup', file=sys.stderr)
                sys.exit(1)
except Exception as e:
    print(f'Backup failed: {e}', file=sys.stderr)
    sys.exit(1)
" "$CACHE_FILE" "$BACKUP_FILE"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Failed to create backup at $BACKUP_FILE" >&2
  exit 1
fi
echo "Created verified backup at $BACKUP_FILE"

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