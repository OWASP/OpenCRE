#!/usr/bin/env bash

set -euo pipefail

INTERVAL_SECONDS="${1:-5}"
TOP_STARTED="${TOP_STARTED:-20}"
RECENT_LOG_LINES="${RECENT_LOG_LINES:-10}"

if [[ -d "./venv" ]]; then
    # shellcheck disable=SC1091
    source "./venv/bin/activate"
fi

cleanup() {
    echo
    echo "[ga-dashboard] stopped"
}
trap cleanup INT TERM

while true; do
    clear
    echo "OpenCRE GA Dashboard  $(date '+%Y-%m-%d %H:%M:%S')  (refresh=${INTERVAL_SECONDS}s)"
    echo "Press Ctrl-C to stop"
    echo

    python - <<'PY'
from datetime import datetime, timezone
from rq import Queue
from rq.registry import StartedJobRegistry, FailedJobRegistry, DeferredJobRegistry, ScheduledJobRegistry
from application.utils import redis

queue_names = ["high", "default", "low", "ga"]
conn = redis.connect()

print("Queue status")
print("-----------")
for qn in queue_names:
    q = Queue(qn, connection=conn)
    started = StartedJobRegistry(qn, connection=conn).get_job_ids()
    failed = FailedJobRegistry(qn, connection=conn).get_job_ids()
    deferred = DeferredJobRegistry(qn, connection=conn).get_job_ids()
    scheduled = ScheduledJobRegistry(qn, connection=conn).get_job_ids()
    print(
        f"{qn:7} queued={len(q):4} started={len(started):3} "
        f"failed={len(failed):3} deferred={len(deferred):3} scheduled={len(scheduled):3}"
    )

print("\nStarted GA jobs")
print("---------------")
ga_q = Queue("ga", connection=conn)
ga_started = StartedJobRegistry("ga", connection=conn).get_job_ids()
now = datetime.now(timezone.utc)
if not ga_started:
    print("(none)")
else:
    top_n = int(__import__("os").environ.get("TOP_STARTED", "20"))
    for jid in ga_started[:top_n]:
        job = ga_q.fetch_job(jid)
        if not job:
            print(f"- {jid} | <missing>")
            continue
        started_at = getattr(job, "started_at", None)
        age = "?"
        if started_at is not None:
            age = str(now - started_at).split(".", 1)[0]
        print(f"- {jid} | age={age} | {job.description}")

needle = {
    "CAPEC->DevSecOps Maturity Model (DSOMM)",
    "DevSecOps Maturity Model (DSOMM)->CAPEC",
}
hits = []
for bucket, ids in (
    ("queued", ga_q.job_ids),
    ("started", ga_started),
    ("failed", FailedJobRegistry("ga", connection=conn).get_job_ids()),
    ("deferred", DeferredJobRegistry("ga", connection=conn).get_job_ids()),
    ("scheduled", ScheduledJobRegistry("ga", connection=conn).get_job_ids()),
):
    for jid in ids:
        job = ga_q.fetch_job(jid)
        if not job:
            continue
        desc = (job.description or "").strip()
        if desc in needle:
            hits.append((bucket, jid, desc))

print("\nCAPEC<->DSOMM status")
print("--------------------")
if not hits:
    print("(not present in ga queue/registries)")
else:
    for bucket, jid, desc in hits:
        print(f"- {bucket:9} {jid} | {desc}")
PY

    echo
    echo "Recent GA worker log signals"
    echo "----------------------------"
    rg -n "ga: |Successfully completed|exception raised|Transient GA error|Performing GraphDB queries" "worker-"*.log -S \
        | tail -n "${RECENT_LOG_LINES}" || true

    sleep "${INTERVAL_SECONDS}"
done
