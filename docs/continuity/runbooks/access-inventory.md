# Continuity runbook: Access inventory

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Verify that a second person can reach every system needed to run the other continuity runbooks. Do **not** print secret values.

## What this is for

A second maintainer should be able to restart Heroku and see live DNS. This runbook checks whether that access is in place.

## Prerequisites

Install (or confirm) these CLIs:

| Tool | Install |
|---|---|
| `gh` | https://cli.github.com |
| `heroku` | https://devcenter.heroku.com/articles/heroku-cli |
| `gcloud` | https://cloud.google.com/sdk/docs/install |
| `terraform` | for Path A IaC (`make gcp-iac-validate`) |
| `dig` | DNS lookups (`bind-tools` / macOS default) |
| `psql`, `docker`, `python3` | backup, local stack, import |

Also:

- GitHub access to `OWASP/OpenCRE`
- `heroku login` if the CLI says you are not logged in
- **Cloudflare** login for the zone that holds `opencre.org` (registrar is GoDaddy; nameservers are delegated to Cloudflare). Rob owns this.
- Rob (Cloudflare / GoDaddy) / Spyros (Heroku team) if a check fails — this runbook only **detects** missing access

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity access-inventory runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/access-inventory.md

Repo: OWASP/OpenCRE. Prod Heroku app: opencreorg. Staging: tmp-cre. Public site: https://opencre.org.

Check each system in the table. Report PASS/FAIL/UNKNOWN per row.
Never print secret values (DATABASE_URL, API keys, heroku config dumps). For config vars, say only SET or UNSET.
Do not change IAM, add collaborators, or edit DNS unless I explicitly ask after the report.
If heroku/gh is not authenticated, stop and tell me the exact login command.
```

## Steps

1. GitHub repo: `gh repo view OWASP/OpenCRE --json name,viewerPermission,url` — need `ADMIN` or `MAINTAIN` to manage Actions environments and this project.
2. GitHub Actions environments used by deploys/backups: `opencreorg`, `tmp-cre`, `Heroku-DB-Backup`, `gcp-iac` (see `.github/workflows/deploy.yml`, `deploy-staging.yml`, `backup.yml`, `gcp-iac.yml`). Confirm you can open them in the repo Settings UI (the agent cannot always see this; say UNKNOWN if not).
3. Heroku auth: `heroku auth:whoami`. If that succeeds but `heroku apps:info -a opencreorg` fails, refuse (not a maintainer).
4. Heroku prod access: `heroku access -a opencreorg` and `heroku apps:info -a opencreorg`. You must appear on `access`. Note dyno names from `heroku ps -a opencreorg` (expect `web` and `worker` from `Procfile`).
5. Heroku staging: `heroku access -a tmp-cre` (FAIL is allowed if staging is unused; record it).
6. Config keys present (names only): `heroku config:get DATABASE_URL -a opencreorg >/dev/null && echo DATABASE_URL=SET`. Repeat for `REDIS_URL`, `NEO4J_URL`, and any `OPENAI` / `GOOGLE` / `GEMINI` / `VERTEX` keys you find via `heroku config -a opencreorg --shell | cut -d= -f1` (names only).
7. Domain: `dig +short opencre.org A` and `dig +short www.opencre.org`. Record targets. Registrar is **GoDaddy**; the zone is **delegated to Cloudflare** (live DNS is Cloudflare). Confirm the human can open the Cloudflare zone for `opencre.org`. Do not treat GoDaddy as the live DNS console.
8. Addons: `heroku addons -a opencreorg` (names/plans only).
9. CLI tools on this machine: `heroku`, `gh`, `gcloud`, `terraform`, `psql`, `docker`, `python3`.

## Done when

A table exists (issue comment or chat) with every row PASS/FAIL/UNKNOWN and **no secret values**. FAIL rows have an owner (who can grant access).

## If it fails

Missing Heroku collaborator → existing Heroku admin adds the person on `opencreorg` (do not share the API key in Slack). Missing Cloudflare / GoDaddy → Rob. Missing GitHub permission → org/repo admin.
