# Agents: OpenCRE Continuity

Existing maintainers only. Index: [`README.md`](README.md). Root policy: [`AGENTS.md`](../../AGENTS.md). Runbook skill: [`runbooks/AGENTS.md`](runbooks/AGENTS.md).

Each runbook has a paste-ready **agent prompt**. Also read subdirectory `AGENTS.md` files when that area applies (`infra/gcp/AGENTS.md`, `scripts/gcp/AGENTS.md`, `scripts/db/AGENTS.md`).

## Refuse if not a maintainer

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

## Hard rules

- Default Heroku app **`opencreorg`**. Staging is **`tmp-cre`**. If unnamed, stop and ask.
- Makefile / `scripts/` only. Never compute gap analysis on production.
- Never dump `heroku config` values. Config vars: SET or UNSET only.
- Destructive prod SQL needs `I_UNDERSTAND_OPENCREORG_PROD_DB_DESTRUCTIVE_ACTION`.
- Do not commit or push unless asked.

## GCP LLM (Path A)

Plan and secrets: [`infra/gcp/README.md`](../../infra/gcp/README.md). Agent file: [`infra/gcp/AGENTS.md`](../../infra/gcp/AGENTS.md). Runbook: [`runbooks/gcp-iac.md`](runbooks/gcp-iac.md).
