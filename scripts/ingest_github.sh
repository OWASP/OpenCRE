#!/usr/bin/env bash
# Point-and-shoot GitHub ingest (positional URL — Make cannot parse https:// goals).
# Usage:
#   ./scripts/ingest_github.sh https://github.com/OWASP/ASVS
#   ./scripts/ingest_github.sh https://github.com/OWASP/ASVS --ingest_keep_all
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ $# -lt 1 ]]; then
  echo "usage: $0 https://github.com/owner/repo [--ingest_keep_all] [--ingest_branch BRANCH]" >&2
  exit 2
fi
URL="$1"
shift
if [[ -d ./venv ]]; then
  # shellcheck disable=SC1091
  source ./venv/bin/activate
fi
export PYTHONPATH=.
exec python cre.py --ingest_github "$URL" "$@"
