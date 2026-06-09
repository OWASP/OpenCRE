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

echo "Importing latest MITRE CWE data into $CACHE_FILE"
exec python "$ROOT_DIR/cre.py" --cwe_in --cache_file "$CACHE_FILE"
