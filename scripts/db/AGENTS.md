# Agents: production DB wrappers

Existing maintainers only. Continuity: [`docs/continuity/runbooks/AGENTS.md`](../../docs/continuity/runbooks/AGENTS.md). Backup: [`docs/continuity/runbooks/production-db-backup.md`](../../docs/continuity/runbooks/production-db-backup.md). Surgery: [`docs/continuity/runbooks/production-db-surgery.md`](../../docs/continuity/runbooks/production-db-surgery.md).

Use `scripts/db/*` only — never ad-hoc `heroku pg:psql` against prod unless the human re-approves after a wrapper failure.

## Refuse if not a maintainer

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

## Do

- Default `APP_NAME=opencreorg`. Stop if the app is unnamed.
- Always capture a finished Heroku backup first (`scripts/db/common.sh`).
- Destructive SQL (`DELETE` / `DROP` / `TRUNCATE` / irreversible `ALTER`) or full `SYNC_TABLES=all` (drops schema `public`) requires the human to type **exactly**  
  `I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION`  
  then `CONFIRM_DESTRUCTIVE` with that same string. Do not accept paraphrases.

## Do not

- Print `DATABASE_URL` or backup URLs that contain credentials.
- Skip backup (`BACKUP_MANDATORY`).
- Point import or surgery at production unless the named runbook and confirmation are in place.
