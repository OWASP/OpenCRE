# Continuity runbook: Staging bootstrap

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Provision or refresh Heroku staging (`tmp-cre` / a named staging app) from prod + local SQLite using `scripts/setup-heroku-staging.sh`.

## What this is for

Need a prod-like app that is not `opencreorg`. Deploy workflow for staging is `.github/workflows/deploy-staging.yml` (branch `staging` → `tmp-cre`).

## Prerequisites

- Human supplies `PROD_APP`, `STAGING_APP`, and `LOCAL_SQLITE_DB` (absolute path)
- Heroku permission to create/manage the staging app
- Docker / local postgres as required by the script header
- This can copy **prod env vars** to staging. Never paste that file into GitHub.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity staging-bootstrap runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/staging-bootstrap.md
- scripts/setup-heroku-staging.sh (header: required env and flags)

Do not run the script until I set PROD_APP, STAGING_APP, and LOCAL_SQLITE_DB.
Default prod is opencreorg; do not treat staging as prod.
Flags: --embeddings / --gap_analysis vs full sync — use what I asked.
Never print env files the script writes. --delete is teardown; require an explicit DESTROY_STAGING confirmation.
```

## Steps

1. Read the script header. Required: `PROD_APP`, `STAGING_APP`, `LOCAL_SQLITE_DB`.
2. Confirm you are **not** passing `STAGING_APP=opencreorg`.
3. Run what the human asked, for example:  
   `PROD_APP=opencreorg STAGING_APP=tmp-cre LOCAL_SQLITE_DB=/abs/path/standards_cache.sqlite bash scripts/setup-heroku-staging.sh --gap_analysis`
4. Health against the staging hostname the script prints (not www.opencre.org unless they share DNS — they should not).
5. Teardown only with `--delete` after the human types `DESTROY_STAGING`.

## Done when

Staging app boots, script exit 0. Issue comment: app name + flags used, no secrets.

## If it fails

`pg_restore` / SSL issues are documented in the script comments. Do not “fix” by pointing the script at prod as `STAGING_APP`.
