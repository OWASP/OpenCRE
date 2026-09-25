# Continuity runbook: Production health

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

HTTP-only checks for https://opencre.org: gap analysis cache, chatbot shell, REST lists. This is the weekly automation prompt in `AGENTS.md`, written so a person can run it with their agent.

## What this is for

“Is prod down?” and “is map analysis empty/503?” before touching Heroku. Also chatbot: SPA must load; unauthenticated `/completion` must be **401** (not 404/500/503).

## Prerequisites

- Network to opencre.org
- Local Python able to run `scripts/monitor_*.py` (venv from `make install-python` is enough; no Heroku needed for a pure HTTP check)
- Heroku CLI only if you then restart/rollback

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity production-health runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/production-health.md
- AGENTS.md section "Weekly prod GA & data completeness"

Use https://opencre.org (not localhost). Never compute gap analysis on Heroku. Never send authenticated chatbot prompts (cost + secrets).
Run the Makefile monitor/verify targets, plus GET /rest/v1/standards and /rest/v1/ga_standards (expect non-empty JSON lists).
Write JSON under tmp/ (gitignored). Summarize exit codes and failing pairs/checks.
If something fails, recommend the next continuity runbook (restart, rollback, gap-analysis-ops, catalog-import-and-sync) — do not run those unless I ask.
```

## Steps

1. `mkdir -p tmp`
2. `make monitor-ga-health-prod` — `scripts/monitor_ga_health.py`. Exit 1 = incomplete pairs and/or HTTP 503 (Neo4j/Redis fallback regression). Exit 2 = config/request failure.
3. `make verify-ga-complete-prod` — `scripts/verify_ga_completeness.py`. Incomplete pairs mean the **cache** is short, not “run GA on Heroku”.
4. `make monitor-chatbot-health-prod` — SPA loads; `/completion` is 401 when logged out. The script also flags a broken webpack `sanitize` interop. Do **not** log in and send a prompt.
5. `curl -sS https://www.opencre.org/rest/v1/standards | python3 -c "import json,sys; d=json.load(sys.stdin); print(type(d).__name__, len(d) if hasattr(d,'__len__') else d)"` — non-empty.
6. Same for `https://www.opencre.org/rest/v1/ga_standards`.
7. Optional if you have Heroku: `heroku ps -a opencreorg` (dyno state only).

## Interpreting results

| Symptom | Next runbook |
|---|---|
| Homepage 5xx / dynos crashed | [restart-production](restart-production.md), then rollback |
| GA 503 or empty `result` | [gap-analysis-ops](gap-analysis-ops.md) — backfill **locally**, never on prod |
| Chatbot SPA 200 but `/completion` 500/503 | restart web; if still bad, [rollback](rollback-production.md) |
| `/completion` 404 | routing/deploy problem — [deploy-production](deploy-production.md) |
| REST standards empty | catalog/data — [catalog-import-and-sync](catalog-import-and-sync.md) (gated) |

## Done when

All three make targets exit 0 (or failures are listed with the recommended next runbook). JSON files exist under `tmp/`. No prompts sent to the LLM, no config dumps.

## If it fails

Do not “just run backfill on Heroku”. Prod is cache-only; a miss should 404, not compute.
