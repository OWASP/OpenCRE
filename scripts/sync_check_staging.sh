#!/usr/bin/env bash
# Print the stack tip on GitHub vs the commit the staging web image was built from.
# Usage: STAGING_HOST=user@staging-host ./scripts/sync_check_staging.sh [branch]
set -euo pipefail
BRANCH="${1:-feat/answer-feedback}"
HOST="${STAGING_HOST:?set STAGING_HOST, e.g. user@host}"
git fetch -q origin "$BRANCH"
TIP="$(git rev-parse --short origin/"$BRANCH")"
# Staging is rsynced from a worktree checked out at the tip; compare file content, not a SHA.
LOCAL="$(git ls-tree -r origin/"$BRANCH" --name-only -- application/utils/comprehension | xargs -I{} git show origin/"$BRANCH":{} | shasum | cut -c1-12)"
REMOTE="$(ssh -n -o BatchMode=yes "$HOST" 'cd /home/sg/Projects/OpenCRE && for f in $(find application/utils/comprehension -type f -name "*.py" | sort); do cat "$f"; done | shasum | cut -c1-12')"
echo "GitHub $BRANCH tip: $TIP"
echo "comprehension code hash  github=$LOCAL  staging=$REMOTE"
