# Continuity runbook: Restart production

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Bounce Heroku dynos for `opencreorg` when the site or worker is wedged. This is the “restart the server” easy-fix.

## What this is for

Hung web process, dead worker (RQ / gap-analysis queue), or a one-off memory event. Prefer this before rollback if the current release was fine yesterday.

## Prerequisites

- `heroku auth:whoami` works and you are on `heroku access -a opencreorg`
- Human has named the app, or agreed the default **`opencreorg`**
- Optional: production-health runbook afterward

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity restart-production runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/restart-production.md

Default app is Heroku opencreorg. Confirm the app name with me before restarting.
Do not restart tmp-cre unless I named staging.
Do not rollback, deploy, or change config.
Never paste heroku config values.
After restart: heroku ps, a short log sample, and curl https://www.opencre.org/ (expect HTTP 200). Then recommend the production-health runbook.
```

## Steps

1. Confirm app: default `opencreorg`. Stop if ambiguous.
2. Snapshot: `heroku ps -a opencreorg` and `heroku releases -a opencreorg -n 5`.
3. Restart:
   - Both process types: `heroku ps:restart -a opencreorg`
   - Web only: `heroku ps:restart web -a opencreorg`
   - Worker only: `heroku ps:restart worker -a opencreorg`
4. Wait until `heroku ps -a opencreorg` shows `up` (not `crashed`).
5. `heroku logs -a opencreorg -n 80` — look for boot errors / release-phase `ALEMBIC_GUARDRAIL_FAIL`. Do not paste lines that contain connection strings.
6. `curl -sI https://www.opencre.org/ | head -n 15` — expect 200. If 503, continue to [production-health](production-health.md); if still dead after a few minutes, consider [rollback](rollback-production.md).

`Procfile` processes: `web` (gunicorn), `worker` (`cre.py --start_worker`), `release` (alembic guardrail — runs on deploy, not on `ps:restart`).

## Done when

Dynos are `up`, homepage returns 200, and the issue comment lists what was restarted (web / worker / both) with timestamps. No secrets.

## If it fails

Crash loop → logs, then rollback. Guardrail messages belong to [deploy](deploy-production.md), not restart. Worker-only failures can leave the site up while GA jobs stall.
