#!/bin/zsh
# Detached six-lever d1 experiment runner (survives terminal close).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a
export PYTHONPATH=. FLASK_CONFIG=development NO_LOAD_GRAPH_DB=1
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p logs tmp/oie_owasp_eval/experiments/d1_levers
LOG="logs/d1_levers_${RUN_TS}.log"
echo "$RUN_TS" > logs/d1_levers_latest.runid
echo "$LOG" > logs/d1_levers_latest.logpath
echo "START $RUN_TS $(date -u)" | tee "$LOG"
# setsid + nohup so nested Module C subprocesses are not SIGHUP'd
if command -v setsid >/dev/null 2>&1; then
  WRAP=(setsid)
else
  WRAP=()
fi
${WRAP[@]} nohup ./venv/bin/python -u scripts/oie_owasp_eval/run_d1_lever_experiments.py \
  --cache_file 'postgresql://cre:password@127.0.0.1:5432/cre_prodclone' \
  "$@" \
  >>"$LOG" 2>&1 &
echo $! | tee logs/d1_levers_latest.pid
disown || true
echo "LOG=$LOG pid=$(cat logs/d1_levers_latest.pid)"
