# OpenCRE Continuity

**Tag: existing maintainers only.**

This is the bus-factor pack: a second maintainer can **operate, diagnose, and recover** public OpenCRE when Spyros is unavailable. It is not a contributor onboarding guide and not a GSoC workstream.

GitHub: label `existing-maintainers-only` on one issue per runbook; board title **OpenCRE Continuity** (tag: existing maintainers only). Close or comment on the card when a *second* maintainer has executed it (or a dry-run, where noted).

## What we want

1. **Someone else can keep the site up.** Restart, rollback, read logs, and tell whether https://opencre.org is healthy — without waiting for one person.
2. **Someone else can touch the data safely.** Backup first. Never compute gap analysis on Heroku (`opencreorg` is cache-only). Destructive SQL and full DB sync require the exact confirmation phrase in [`scripts/db/AGENTS.md`](../../scripts/db/AGENTS.md).
3. **Access is shared, secrets are not pasted.** Second-person Heroku access, GitHub admin/Actions environments, and domain DNS (GoDaddy registrar, Cloudflare DNS) are in the access-inventory runbook. Values from `heroku config` never go into issues, chat, or screenshots.
4. **Semi-technical maintainers can run procedures with their agent.** Every runbook has a paste-ready **agent prompt** and shared instructions in [`runbooks/AGENTS.md`](runbooks/AGENTS.md). The human confirms the target app and any destructive step; the agent runs the Makefile / `scripts/` wrappers already in root `AGENTS.md`.

Out of scope here: product features (OWASP Agent, RAG, AWS), mapping campaigns, and GSoC pipeline development. Those stay on their own issues.

## Hard rules (every runbook)

- Target app defaults to **`opencreorg`** (prod). Staging is **`tmp-cre`**. If the human did not name the app, stop and ask.
- Prefer **Makefile targets** and `scripts/` over ad-hoc `docker run` / raw `psql`.
- **Do not compute gap analysis on production.** Cache miss → 404 is expected. Backfill locally, then sync tables if a maintainer approved it.
- **Do not dump secrets.** Report only whether a config var is set, never its value.
- **Do not commit or push** unless the human asked.
- Production DB: `scripts/db/*` only. Fresh backup is mandatory. Destructive work needs  
  `CONFIRM_DESTRUCTIVE=I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION`.
- If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

## How a semi-technical maintainer runs one

1. Open this repo in your coding agent.
2. Open the runbook below.
3. Paste the **Agent prompt** into chat.
4. Confirm the target (`opencreorg` vs `tmp-cre`) when the agent asks.
5. Comment the outcome on the GitHub issue (commands run, exit codes, no secrets).

## Runbooks

Agent instructions for every runbook: [`runbooks/AGENTS.md`](runbooks/AGENTS.md). Pack-level: [`AGENTS.md`](AGENTS.md). GCP: [`infra/gcp/AGENTS.md`](../../infra/gcp/AGENTS.md). DB wrappers: [`scripts/db/AGENTS.md`](../../scripts/db/AGENTS.md).

| Runbook | When to use |
|---|---|
| [Access inventory](runbooks/access-inventory.md) | First time, or “do I even have the keys?” |
| [Restart production](runbooks/restart-production.md) | Site hung, dyno crashed, “turn it off and on” |
| [Rollback production](runbooks/rollback-production.md) | Bad deploy, need previous Heroku release |
| [Production health](runbooks/production-health.md) | Is GA / chat / REST actually up? |
| [Production DB backup](runbooks/production-db-backup.md) | Before any prod data change, or on demand |
| [Production DB surgery](runbooks/production-db-surgery.md) | Targeted SQL on Heroku Postgres |
| [Deploy production](runbooks/deploy-production.md) | Guardrail + how prod actually ships |
| [Catalog import and sync](runbooks/catalog-import-and-sync.md) | Refresh mappings locally; optional gated prod sync |
| [Gap analysis ops](runbooks/gap-analysis-ops.md) | Incomplete map analysis on prod |
| [Staging bootstrap](runbooks/staging-bootstrap.md) | Recreate or refresh `tmp-cre` |
| [Local stack](runbooks/local-stack.md) | Reproduce prod-class failures on a laptop |
| [GCP LLM IaC](runbooks/gcp-iac.md) | New Gemini project on the operator’s billing (Path A) |

## Related

- Operational command list: [`AGENTS.md`](../../AGENTS.md)
