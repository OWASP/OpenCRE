# OpenCRE Agent Instructions

Cursor agents working in this repo must follow the rules in `.cursor/rules/`.

## Quick start

1. **Requirements gate** — If goal, success criteria, `@` file refs, or constraints are missing, stop and ask (`requirements-gate.mdc`).
2. **Plan first** — Non-trivial or multi-file work requires a plan and user approval before coding (`plan-first-workflow.mdc`, `multi-agent-workflow.mdc`).
3. **Verify** — After code changes, run checks and iterate until green (`verifiable-goals.mdc`):
   - `make lint`
   - `make mypy`
   - `make test`
   - `make frontend` (if frontend touched)
4. **Review** — Substantive work needs independent judge/subagent review (`multi-agent-workflow.mdc`).
5. **Production gap analysis** — On Heroku/opencreorg, gap analysis is cache-only: serve precomputed rows from Postgres; do not compute GA on production (cache miss → 404).

## Operational scripts

Prefer existing Makefile targets and `scripts/` helpers over ad-hoc Docker, GA, import, or prod-DB setup. Read script headers or `--help` for env vars and flags; do not reimplement their logic.

### Local Docker services

Use Makefile targets — do not hand-roll `docker run`:

```bash
make docker-neo4j      # Neo4j (7474/7687)
make docker-redis      # Redis Stack (6379/8001)
make docker-postgres   # local Postgres (5432, cre/password)
make start-containers  # neo4j + redis only
make migrate-upgrade   # after postgres is up
```

Reset volumes: `make docker-neo4j-rm` / `make docker-redis-rm`.

### Imports and Neo4j populate

```bash
make import-all        # full standards import via scripts/import-all.sh
make import-projects   # skip core CRE import (CRE_SKIP_IMPORT_CORE=1)
make import-neo4j      # populate Neo4j from cache
```

`scripts/import-all.sh` handles parallel importers, SQLite export, and verification. For embeddings-only SQLite → Postgres push, use `scripts/sync_embeddings_table.py` (see its docstring).

### Gap analysis (local compute, prod verify)

**Local backfill** (starts containers, workers, migrations — see `scripts/backfill_gap_analysis.sh`):

```bash
make backfill-gap-analysis              # parallel workers + --ga_backfill_missing
make backfill-gap-analysis-sync         # Neo4j populate + backfill without queue
make sync-gap-analysis-table-local      # upsert material rows sqlite → local Postgres
```

**Prod / staging checks** (HTTP only — never compute GA on opencreorg):

```bash
make verify-ga-complete-prod    # scripts/verify_ga_completeness.py
make monitor-ga-health-prod     # scripts/monitor_ga_health.py (503 / empty result alerts)
make verify-ga-parity-local     # scripts/verify_ga_postgres_neo_parity.py
```

Table sync between databases: `scripts/sync_gap_analysis_table.py`, `scripts/sync_embeddings_table.py`.

### Production DB (Heroku opencreorg)

Use `scripts/db/*` — never raw destructive `psql` against prod without these wrappers. All flows capture and wait for a fresh Heroku backup first (`scripts/db/common.sh`).

```bash
scripts/db/backup-opencreorg.sh                                    # backup only
scripts/db/surgery-opencreorg.sh --sql-file path/to/change.sql     # targeted SQL
scripts/db/surgery-opencreorg.sh --sql-file … --destructive        # DELETE/DROP/TRUNCATE
scripts/db/sync-local-to-opencreorg.sh [--table node]…             # local → prod sync
```

Destructive surgery requires `CONFIRM_DESTRUCTIVE=I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION` (exact phrase). Override app: `APP_NAME=opencreorg`. See `production-db-ops-safety.mdc`.

After prod GA cache changes, verify with `make verify-ga-complete-prod` / `make monitor-ga-health-prod`.

### Weekly prod GA & data completeness (Cursor Automation)

Schedule a **Cursor Automation** (not GitHub Actions) to run weekly — prod is cache-only; checks are HTTP + repo scripts only.

| Setting | Value |
|---------|--------|
| Trigger | Cron: `0 9 * * 1` (Mondays 09:00) |
| Repo | `OWASP/OpenCRE`, branch `main` |
| Tools | None required (cloud agent uses repo checkout) |

**Agent prompt (paste into Automations editor):**

```
Weekly OpenCRE prod GA and data completeness for opencreorg.

1. python3 scripts/monitor_ga_health.py --base-url https://opencre.org --output-json tmp/prod-ga-health.json
2. python3 scripts/verify_ga_completeness.py --base-url https://opencre.org --output-json tmp/prod-ga-completeness.json
3. Confirm /rest/v1/standards and /rest/v1/ga_standards return non-empty lists.
4. If incomplete_pairs > 0 or non-zero exit: list failing pairs/buckets; recommend AGENTS.md Operational scripts (local backfill + scripts/sync_gap_analysis_table.py). Do not compute GA on Heroku or run destructive prod DB ops without explicit approval.
5. If all pass: report complete/total pairs and standards counts.
```

Create via **Cursor → Automations → New** (Agents Window). Do not hand-roll docker/GA setup in the automation prompt.

### Staging bootstrap

`scripts/setup-heroku-staging.sh` — provisions staging from prod + local SQLite; supports `--embeddings`, `--gap_analysis`, or full sync. Requires `PROD_APP`, `STAGING_APP`, `LOCAL_SQLITE_DB`.

### Deploy / migrations

Before deploy or `flask db upgrade`: `make alembic-guardrail` (or `python scripts/check_alembic_revision_guardrail.py`).

## Rule index

| Rule | Purpose |
|------|---------|
| `requirements-gate.mdc` | Clarifying questions + requirements template |
| `complete-ticket.mdc` | Ticket gate for `.md`/`.txt` files; uses `requirements-gate` template + coding standards |
| `plan-first-workflow.mdc` | Plan Mode before non-trivial edits |
| `multi-agent-workflow.mdc` | Big changes, approval gates, builder ≠ judge |
| `verifiable-goals.mdc` | Lint, mypy, test, CI — show evidence |
| `never-assume.mdc` | No guessing; complete code; minimal scope |
| `tdd-workflow.mdc` | Test-first for new behavior and importers |
| `autonomous-workflow.mdc` | Execute after approval; no unsolicited commits |
| `context-management.mdc` | `/clear`, `@` refs, stale context recovery |
| `production-db-ops-safety.mdc` | Destructive prod DB confirmation |
| `alembic-deploy-guardrail.mdc` | Pre-deploy migration guardrail |

## OpenCRE commands

```bash
make lint              # black + frontend prettier
make mypy              # Python typecheck
make test              # Python unittest suite
make frontend          # yarn build (when TS/TSX changed)
make alembic-guardrail # before deploy/migration ops
make install-python    # includes `playwright install` for Python embeddings (prompt_client) — not frontend e2e; do not remove when adding Cypress
```
