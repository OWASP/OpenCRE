# Continuity runbook: Deploy production

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

How `opencreorg` actually ships, and the Alembic guardrail that must pass before a slug should run.

## What this is for

Understand auto-deploy, kick a manual deploy, or diagnose a release-phase failure. Not a request to “ship my laptop branch to prod”.

## Prerequisites

- Read `.github/workflows/deploy.yml` (prod) and `Procfile`
- Human must explicitly ask to **dispatch** a deploy. Listing releases is read-only and OK.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity deploy-production runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/deploy-production.md
- .github/workflows/deploy.yml
- Procfile
- scripts/check_alembic_revision_guardrail.py

Explain current prod release vs origin/main. Do not dispatch a GitHub Actions deploy or git push to Heroku unless I explicitly say DEPLOY_OPENCREORG.
Never force-push GitHub main.
If checking the guardrail against prod, use heroku config:get DATABASE_URL only as an env var in the process — never print it.
```

## How prod deploys

1. On `main`, after workflows **Test**, **Lint Code Base**, and **Test-e2e** complete, `Deploy to OPENCREORG` runs (also `workflow_dispatch`).
2. The job force-pushes `origin/main` to `https://git.heroku.com/opencreorg.git` and bumps an annotated `v*` tag.
3. Heroku `release:` runs `python scripts/check_alembic_revision_guardrail.py`. If the DB’s `alembic_version` is not in `migrations/versions`, the release **fails** and the old slug stays — that is intentional.
4. Then `web` and `worker` boot from `Procfile`.

Staging is a separate workflow: `.github/workflows/deploy-staging.yml` → app `tmp-cre` from branch `staging`.

## Steps (read-only default)

1. `git fetch origin` and compare `origin/main` to `heroku releases -a opencreorg -n 5`.
2. GitHub Actions: `gh run list --repo OWASP/OpenCRE --workflow "Deploy to OPENCREORG" --limit 5`.
3. Optional guardrail against prod DB (only if asked):  
   `DATABASE_URL="$(heroku config:get DATABASE_URL -a opencreorg)" make alembic-guardrail`  
   Do not echo `DATABASE_URL`.

## Steps (deploy — only after `DEPLOY_OPENCREORG`)

1. Confirm `main` is the intended SHA and CI is green: `gh pr checks` is N/A for main; use `gh run list`.
2. `gh workflow run "Deploy to OPENCREORG" --repo OWASP/OpenCRE` (needs permission on environment `opencreorg`).
3. Watch the run. Then [production-health](production-health.md).

Do **not** `git push --force heroku` from a laptop unless a maintainer is following the workflow file on purpose; the Actions path is the documented one.

## Done when

Read-only: report of current release vs `origin/main` and last deploy run.  
Deploy: new Heroku release `up`, homepage 200, health runbook clean.

## If it fails

`ALEMBIC_GUARDRAIL_FAIL` → stop shipping slugs that lack the DB revision. Reconcile lineage; do not `flask db downgrade` on prod without a written plan. e2e workflow noise is not a failed Heroku release.
