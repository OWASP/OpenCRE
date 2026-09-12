# Agents: continuity runbooks

Existing maintainers only. Pack index: [`../README.md`](../README.md). Pack agent file: [`../AGENTS.md`](../AGENTS.md). Root: [`AGENTS.md`](../../../AGENTS.md).

These runbooks are the procedures. This file is the agent skill for this directory (any coding agent; not Cursor-specific).

## Refuse if not a maintainer

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

## Hard rules

- Default Heroku app **`opencreorg`**. Staging is **`tmp-cre`**. If unnamed, stop and ask.
- Makefile / `scripts/` only. Never compute gap analysis on production.
- Never dump `heroku config` values. Config vars: SET or UNSET only.
- Destructive prod SQL needs exactly `I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION`. See [`scripts/db/AGENTS.md`](../../../scripts/db/AGENTS.md).
- Do not commit or push unless asked.
- Do not add collaborators, edit DNS, or dispatch a deploy unless the human explicitly asks after the report.

## CLI tools (install if missing)

| Tool | Why |
|---|---|
| `gh` | GitHub repo, Actions, environments |
| `heroku` | Prod app `opencreorg` |
| `gcloud` | Path A GCP IaC (`infra/gcp/`) |
| `terraform` | `make gcp-iac-validate` / IaC plan |
| `dig` | DNS checks |
| `psql`, `docker`, `python3` | Backup, local stack, import |

## DNS

Registrar is **GoDaddy**. The zone is **delegated to Cloudflare**. Live records are in Cloudflare, not GoDaddy. Do not guess a Google registrar.

## Runbooks

| Intent | Runbook |
|---|---|
| Keys / Heroku / DNS / Cloudflare | [access-inventory.md](access-inventory.md) |
| Restart dynos | [restart-production.md](restart-production.md) |
| Undo a Heroku release | [rollback-production.md](rollback-production.md) |
| Is prod up? GA/chat/REST | [production-health.md](production-health.md) |
| On-demand Postgres backup | [production-db-backup.md](production-db-backup.md) |
| Targeted prod SQL | [production-db-surgery.md](production-db-surgery.md) |
| How prod ships / dispatch | [deploy-production.md](deploy-production.md) |
| Import locally / sync tables | [catalog-import-and-sync.md](catalog-import-and-sync.md) |
| Map analysis cache | [gap-analysis-ops.md](gap-analysis-ops.md) |
| Heroku staging | [staging-bootstrap.md](staging-bootstrap.md) |
| Laptop docker/postgres | [local-stack.md](local-stack.md) |
| GCP Gemini / LLM billing | [gcp-iac.md](gcp-iac.md) — also [`infra/gcp/AGENTS.md`](../../../infra/gcp/AGENTS.md) |
