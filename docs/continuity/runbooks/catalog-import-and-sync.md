# Continuity runbook: Catalog import and sync

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Refresh CRE/standards **locally** (`make import-all`). Pushing tables to Heroku is a separate, gated step. Never point `import-all` at production `DATABASE_URL`.

## What this is for

Stale mappings, missing standard, empty `/rest/v1/standards`. Import is slow and network-heavy. Prod sync can drop the public schema if you sync `all` — treat it like surgery.

## Prerequisites

- Local stack: [local-stack](local-stack.md) (venv, docker postgres/neo4j/redis as needed)
- For prod sync: Heroku collaborator, docker (the sync script uses a postgres client container), and explicit human approval
- Full `SYNC_TABLES=all` reset **drops schema `public`** on the target (`scripts/db/sync-local-to-opencreorg.sh`). Require the destructive confirmation phrase even though the script does not currently check it.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity catalog-import-and-sync runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/catalog-import-and-sync.md
- scripts/db/AGENTS.md
- AGENTS.md imports section
- scripts/import-all.sh (header only unless debugging)

Part A — local import: use Makefile (make import-all / make import-projects / make import-neo4j). Never set CRE_CACHE_FILE or DATABASE_URL to Heroku.
Part B — prod sync: do not run scripts/db/sync-local-to-opencreorg.sh until I name APP_NAME, the --table list (prefer specific tables, not all), and for a full-DB sync I type
I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION
because full sync DROP SCHEMA public.
Prefer --table flags. The wrapper always backups first.
Never print DATABASE_URL.
```

## Steps — A. Local import

1. Confirm you are **not** using a Heroku database URL.
2. `make import-all` (or `make import-projects` to skip core CRE). Implementation: `scripts/import-all.sh`.
3. If graph features need it: `make import-neo4j` (`cre.py --populate_neo4j_db`) against **local** Neo4j.
4. Embeddings-only sqlite→postgres is `python scripts/sync_embeddings_table.py` (see its docstring) — still local unless asked.

## Steps — B. Prod table sync (gated)

1. [Backup](production-db-backup.md) is already inside the wrapper; still tell the human a full sync is destructive.
2. Prefer tables: e.g.  
   `APP_NAME=opencreorg scripts/db/sync-local-to-opencreorg.sh --table node --table gap_analysis`  
   (only the tables the human named).
3. Full sync (`SYNC_TABLES=all`, default): wait for the exact destructive phrase, then run. This `DROP SCHEMA IF EXISTS public CASCADE` on the target when `RESET_TARGET_PUBLIC_SCHEMA=1`.
4. After sync: [production-health](production-health.md). Do not compute GA on Heroku. If GA cache is incomplete, [gap-analysis-ops](gap-analysis-ops.md).

## Done when

Part A: import script verification passed (see `import-all.sh` verify).  
Part B (if requested): wrapper exit 0, backup id recorded, health checks run.

## If it fails

Import verification warnings → do not sync prod. Sync restore errors → stop; use the backup id from the wrapper log (not a URL with credentials).
