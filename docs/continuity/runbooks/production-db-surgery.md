# Continuity runbook: Production DB surgery

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Run a **file of SQL** against Heroku Postgres through `scripts/db/surgery-opencreorg.sh`. Always backups first. Destructive SQL is extra-gated.

## What this is for

Tiny, reviewed fixes (one node, one mapping row) — not a full restore. Full replace is [catalog-import-and-sync](catalog-import-and-sync.md).

## Prerequisites

- Human provided a SQL **file path** in the repo or a gist they own
- Collaborator on `opencreorg`
- If the SQL contains `DELETE` / `DROP` / `TRUNCATE` / irreversible `ALTER`, the human must type **exactly**  
  `I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION`  
  in chat **and** you pass `--destructive` with that env var. Do not accept paraphrases.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity production-db-surgery runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/production-db-surgery.md
- scripts/db/AGENTS.md
- scripts/db/surgery-opencreorg.sh

Default APP_NAME=opencreorg. Stop until I confirm the app and the SQL file path.
Read the SQL file. If it is destructive, do not run it until I type exactly
I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION
in this chat. Then:
CONFIRM_DESTRUCTIVE=I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION \
  scripts/db/surgery-opencreorg.sh --sql-file PATH --destructive
Non-destructive: scripts/db/surgery-opencreorg.sh --sql-file PATH
Never paste DATABASE_URL. Afterward run production-health HTTP checks (not GA compute).
```

## Steps

1. Confirm app and SQL file. Read the file. Classify destructive vs not.
2. If destructive: wait for the exact phrase. If missing `--destructive` while the file deletes rows, **stop** (the wrapper does not parse SQL for DROP).
3. Run the wrapper (it calls `capture_backup_strict` then `psql -f`).
4. `make monitor-ga-health-prod` and homepage curl if the change could affect the site.

## Done when

Script exit 0, backup completed before the SQL, issue comment describes the change in English (not the live connection string).

## If it fails

Backup capture failed → do not retry SQL. SQL error → leave the backup id in the issue; do not “fix” with ad-hoc `heroku pg:psql` unless the human re-approves.
