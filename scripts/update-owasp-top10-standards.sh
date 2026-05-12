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

if ! python -c "import requests" >/dev/null 2>&1; then
  echo "Installing Python dependencies"
  pip install -r "$ROOT_DIR/requirements.txt"
fi

if [[ -f "$CACHE_FILE" ]]; then
  cp "$CACHE_FILE" "$BACKUP_FILE"
  echo "Backed up database to $BACKUP_FILE"
fi

export CRE_NO_NEO4J="${CRE_NO_NEO4J:-1}"
export CRE_NO_GEN_EMBEDDINGS="${CRE_NO_GEN_EMBEDDINGS:-1}"
export CRE_UPSTREAM_MAX_ATTEMPTS="${CRE_UPSTREAM_MAX_ATTEMPTS:-6}"
export CRE_UPSTREAM_RETRY_BACKOFF_SECONDS="${CRE_UPSTREAM_RETRY_BACKOFF_SECONDS:-2}"
export CRE_UPSTREAM_TIMEOUT_SECONDS="${CRE_UPSTREAM_TIMEOUT_SECONDS:-30}"

echo "Refreshing official OpenCRE upstream data in $CACHE_FILE"
python "$ROOT_DIR/cre.py" --upstream_sync --cache_file "$CACHE_FILE"

echo "Reapplying OWASP Top 10 standards and CRE mappings"
python "$ROOT_DIR/cre.py" \
  --owasp_top10_2025_in \
  --owasp_api_top10_2023_in \
  --owasp_kubernetes_top10_2025_in \
  --owasp_llm_top10_2025_in \
  --owasp_aisvs_in \
  --cache_file "$CACHE_FILE"

echo "Selecting preferred Kubernetes Top Ten version"
if python - <<'PY' "$CACHE_FILE"
import sqlite3
import sys

cache_file = sys.argv[1]
name_2025 = "OWASP Kubernetes Top Ten 2025 (Draft)"
name_2022 = "OWASP Kubernetes Top Ten 2022"

conn = sqlite3.connect(cache_file)
cur = conn.cursor()

linked_2025 = cur.execute(
    """
    select count(*)
    from node n
    join cre_node_links l on l.node = n.id
    where n.name = ?
    """,
    (name_2025,),
).fetchone()[0]

if linked_2025 > 0:
    cur.execute("delete from node where name = ?", (name_2022,))
    print(f"Using {name_2025}; removed {name_2022}")
else:
    raise SystemExit(f"{name_2025} not linked")

conn.commit()
conn.close()
PY
then
  :
else
  echo "OWASP Kubernetes Top Ten 2025 (Draft) is unavailable or unmapped, importing 2022"
  python "$ROOT_DIR/cre.py" \
    --owasp_kubernetes_top10_2022_in \
    --cache_file "$CACHE_FILE"
fi

echo "Pruning OWASP Top 10 entries that still have no CRE links"
python - <<'PY' "$CACHE_FILE"
import sqlite3
import sys

cache_file = sys.argv[1]
standard_names = (
    "OWASP Top 10 2025",
    "OWASP API Security Top 10 2023",
    "OWASP Kubernetes Top Ten 2025 (Draft)",
    "OWASP Top 10 for LLM and Gen AI Apps 2025",
    "OWASP AI Security Verification Standard (AISVS)",
)

conn = sqlite3.connect(cache_file)
cur = conn.cursor()

has_2022 = cur.execute(
    "select 1 from node where name = 'OWASP Kubernetes Top Ten 2022' limit 1"
).fetchone()
if has_2022:
    standard_names = standard_names + ("OWASP Kubernetes Top Ten 2022",)

rows = list(
    cur.execute(
        f"""
        select n.id, n.name, coalesce(n.section_id, ''), coalesce(n.section, '')
        from node n
        left join cre_node_links l on l.node = n.id
        where n.name in ({','.join('?' for _ in standard_names)})
        group by n.id
        having count(l.cre) = 0
        """,
        standard_names,
    )
)

for node_id, name, section_id, section in rows:
    cur.execute("delete from node where id = ?", (node_id,))
    print(f"Removed unmapped entry: {name} {section_id} {section}".strip())

conn.commit()
conn.close()
PY
