# Continuity runbook: Gap analysis ops

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Production map analysis is **cache-only**. Fix incompleteness by backfilling **locally**, then syncing cache tables if a maintainer approved. Never compute GA on `opencreorg`.

## What this is for

`make monitor-ga-health-prod` / `verify-ga-complete-prod` failing, HTTP 503 on map analysis, or empty `result` payloads.

## Prerequisites

- Local docker: redis, neo4j, postgres+pgvector ([local-stack](local-stack.md))
- Prod checks: network only
- Prod data change: [catalog-import-and-sync](catalog-import-and-sync.md) part B, approved

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity gap-analysis-ops runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/gap-analysis-ops.md
- AGENTS.md gap analysis section

On Heroku/opencreorg, GA is cache-only: serve precomputed rows; cache miss → 404. Never run --ga_backfill_* against production DATABASE_URL.
First: HTTP health (make monitor-ga-health-prod, make verify-ga-complete-prod).
If incomplete: local backfill only (make backfill-gap-analysis or make backfill-gap-analysis-sync) after local-stack is up.
Do not sync tables to prod unless I name the tables and approve. Then production-health again.
```

## Steps

1. Diagnose (HTTP): `make monitor-ga-health-prod` and `make verify-ga-complete-prod`. Optional REST: `/rest/v1/ga_standards`.
2. If 503: often worker/redis/neo4j path — check `heroku ps -a opencreorg` (worker) and consider [restart](restart-production.md). Still **do not** compute GA on prod.
3. Local backfill (after [local-stack](local-stack.md)):
   - `make backfill-gap-analysis` — `scripts/backfill_gap_analysis.sh` (starts docker, workers, `--ga_backfill_missing`)
   - or `make backfill-gap-analysis-sync` — populate Neo4j + backfill without queue
   - `make verify-ga-parity-local` if you need postgres vs neo parity
4. Copy cache to prod **only if asked**: `scripts/sync_gap_analysis_table.py` or `scripts/db/sync-local-to-opencreorg.sh --table …` as in catalog-import-and-sync. Default destination for `make sync-gap-analysis-table-local` is **local** postgres, not Heroku.
5. Re-run prod HTTP verifies.

## Done when

Prod HTTP checks exit 0, or remaining incomplete pairs are listed with a human decision (accept / sync / restart worker). No GA compute on Heroku.

## If it fails

Local workers dying → redis/neo4j containers (`make docker-redis`, `make docker-neo4j`). Prod still 503 after restart → logs (redact URLs) and a maintainer who knows Neo4j Aura.
