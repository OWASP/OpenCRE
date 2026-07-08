#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/venv"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if ! python -c "import flask" >/dev/null 2>&1; then
  echo "Installing Python dependencies"
  pip install -r "$ROOT_DIR/requirements.txt"
fi

export NO_LOGIN="${NO_LOGIN:-1}"
export INSECURE_REQUESTS="${INSECURE_REQUESTS:-1}"
export FLASK_APP="$ROOT_DIR/cre.py"
export FLASK_CONFIG="${FLASK_CONFIG:-development}"

echo "Starting OpenCRE on http://127.0.0.1:5000"
exec flask run --host 127.0.0.1 --port 5000
