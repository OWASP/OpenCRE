#!/bin/zsh
# Durable local full-pipeline runner (ASVS+AISVS GitHub + B2 arms).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
set -a
# shellcheck disable=SC1091
source .env
set +a
export PYTHONPATH=. FLASK_CONFIG=development
RUN_ID="fullpipe-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p logs tmp/oie_owasp_eval/full_pipeline
echo "$RUN_ID" > logs/full_pipeline_latest.runid
LOG="logs/full_pipeline_${RUN_ID}.log"
echo "START $RUN_ID $(date -u)" | tee "$LOG"
rc=0
./venv/bin/python -u scripts/oie_owasp_eval/run_full_pipeline.py \
  --repos asvs,aisvs,aix,nist,top10,api \
  --cache_file 'postgresql://cre:password@127.0.0.1:5432/cre_prodclone' \
  --run-id "$RUN_ID" \
  --keep-all-knowledge \
  --neighborhood \
  --wipe-queues \
  --out-dir tmp/oie_owasp_eval/full_pipeline \
  >>"$LOG" 2>&1 || rc=$?
echo "EXIT:${rc}" | tee -a "$LOG"
if [[ -f tmp/oie_owasp_eval/full_pipeline/summary.json ]]; then
  echo '==== summary.json ====' | tee -a "$LOG"
  cat tmp/oie_owasp_eval/full_pipeline/summary.json | tee -a "$LOG"
fi
echo FULL_PIPELINE_DONE | tee -a "$LOG"
exit "$rc"
