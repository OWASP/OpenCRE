# Continuity runbook: Production DB backup

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Capture a finished Heroku Postgres backup for `opencreorg` using the wrapper (not ad-hoc `pg_dump`).

## What this is for

Before surgery, table sync, or whenever you want a restore point. Daily capture also exists in `.github/workflows/backup.yml`; this runbook is the **on-demand** path.

## Prerequisites

- `heroku` CLI, logged in, collaborator on `opencreorg`
- `psql` is required by `scripts/db/common.sh` even for backup-only

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity production-db-backup runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/production-db-backup.md
- scripts/db/AGENTS.md
- scripts/db/backup-opencreorg.sh and scripts/db/common.sh

Default APP_NAME=opencreorg. Confirm the app with me if I did not name it.
Run scripts/db/backup-opencreorg.sh (it captures and waits). Do not download the dump to the laptop unless I ask.
Never print DATABASE_URL. Afterward: heroku pg:backups -a opencreorg and quote only backup id + status + time.
```

## Steps

1. Confirm app `opencreorg` (override only with `APP_NAME=...` if the human named staging).
2. `scripts/db/backup-opencreorg.sh`
3. Confirm completion: `heroku pg:backups -a opencreorg` — newest should be `Completed`.
4. Optional download (only if asked): `heroku pg:backups:download -a opencreorg`. Store outside git. Do not commit `*.dump`.

## Done when

The script exits 0 and the latest backup is `Completed`. Issue comment has the backup id (e.g. `b0123`), not a URL with credentials.

## If it fails

`heroku login` / not in `access`. Capture already running → wait (`heroku pg:backups:wait -a opencreorg`). Do not switch `BACKUP_MANDATORY` off.
