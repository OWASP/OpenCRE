# Continuity runbook: Rollback production

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Return `opencreorg` to a previous **Heroku release**. Prod deploys are a force-push to the Heroku `main` git remote (see `.github/workflows/deploy.yml`); rollback is `heroku rollback`, not `git revert` on GitHub.

## What this is for

A deploy that boots but is wrong (500s, broken chatbot bundle, bad migration that the *next* slug cannot start). If dynos are merely stuck, try [restart](restart-production.md) first.

## Prerequisites

- Heroku collaborator on `opencreorg`
- Human explicitly asked to rollback (agent must not do this unprompted)
- You know whether the bad release included a **database migration**. Rolling back the slug does **not** undo Postgres. If the DB moved forward, stop and get a maintainer who understands Alembic before rolling back.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity rollback-production runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/rollback-production.md

Default app: Heroku opencreorg.
List heroku releases and recommend a target. Do NOT run heroku rollback until I type the release id (e.g. v1234) in this chat.
If the bad deploy may have migrated Postgres, stop — rollback of the slug will not reverse the DB. Point me at make alembic-guardrail and scripts/check_alembic_revision_guardrail.py.
Never dump config. After a rollback I approve: heroku ps, homepage curl, then production-health.
```

## Steps

1. Confirm app `opencreorg` and that the human asked for rollback.
2. `heroku releases -a opencreorg -n 15`. Identify current `vN` and the last known-good release.
3. Ask: did that bad release run `flask db upgrade` / add an Alembic revision? If yes or unknown, **stop**.
4. After the human types the exact id: `heroku rollback vNNNN -a opencreorg`.
5. `heroku ps -a opencreorg` until `up`.
6. `curl -sI https://www.opencre.org/ | head -n 15`.
7. If the app will not boot: `heroku logs -a opencreorg -n 120` and look for `ALEMBIC_GUARDRAIL_FAIL` (Procfile `release:` runs `python scripts/check_alembic_revision_guardrail.py`). Guardrail fail means the slug’s migration tree does not contain the DB’s revision — do not keep rolling back blindly.

## Done when

`heroku releases` shows the rolled-back version as current, dynos `up`, homepage 200. Comment the from/to release ids on the GitHub issue.

## If it fails

Guardrail fail → the DB is ahead of the old slug. Forward-fix (deploy a slug that contains those revisions) or restore a backup — that is [production-db-backup](production-db-backup.md) + a human decision, not another rollback.
