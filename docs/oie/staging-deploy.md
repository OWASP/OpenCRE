# Deploying to staging

One script, used by everyone (people and Claude sessions): `scripts/staging_deploy.sh`. Do not hand-roll
`docker build` / `cp` / `compose up` on the homeserver; that is how deploys overwrote each other before.

```bash
scripts/staging_deploy.sh --status                         # what is deployed, who holds the lock
scripts/staging_deploy.sh --branch feat/ext-integration --dry-run   # checks only, changes nothing
scripts/staging_deploy.sh --branch feat/ext-integration    # deploy origin/<branch>
STAGING_SMOKE_TOKEN=<api key or access token> scripts/staging_deploy.sh   # also smoke-tests an authenticated ask
scripts/staging_deploy.sh --rollback pre-deploy-<timestamp>
```

Needs ssh access to the homeserver (`STAGING_HOST`, default `sg@100.74.143.62`) and a clone with `origin` fetched.
Only pushed commits are deployed (it uses `origin/<branch>`).

## What protects against overwrites

- **Lock**: `deploy/staging/.deploy.lock` on the host (created with `mkdir`, so only one deploy wins). A lock older
  than 90 minutes can be broken with `--force`.
- **Ancestry guard**: the host records the deployed commit in `deploy/staging/DEPLOYED_COMMIT`. A deploy is refused unless the
  new commit contains it, so you cannot ship a branch that lacks code already live (merge first, or `--force`).
- **Host-only state check**: refuses if the new tree has no `application/mcp/oauth.py`, or the host lost the
  OAuth nginx routes, the SSE patch in `overlays/mcp/http_app.py`, or the OAuth `.env` settings.
- **Backup** before every deploy: `deploy/staging/backups/pre-deploy-<ts>/` (`.env`, `overlays/mcp`, `nginx.conf`,
  `overlays/api_tokens`) and the previous image tagged `opencre-staging-web:pre-deploy-<ts>`.

## What a deploy changes

`git archive` of the commit is built with `deploy/staging/Dockerfile.hotpatch` into `opencre-staging-web:<short sha>`.
`overlays/mcp` and `overlays/api_tokens` get the tree's files, except `overlays/mcp/http_app.py`, which is 3-way merged
(`git merge-file`: host copy, previously deployed version, new version) so the host-only `SseFirstByteMiddleware` patch survives.
`flask db upgrade head` runs in a one-off container with the tree's `migrations/` mounted (the image does not carry them).
Then `:latest` is retagged and `web mcp edge` are recreated with `--force-recreate` (needed to pick up env changes).
`.env` values, `overlays/edge/nginx.conf` and the database contents are never modified by the script.

## Smoke checks

`/` 200, OAuth metadata 200, `/mcp` without a token 401, `/register` 201 (the test client is deleted again), and, with
`STAGING_SMOKE_TOKEN`, an authenticated MCP `ask`. A failed check exits non-zero and prints the rollback command.

## First run / host setup

The host needs `deploy/staging/DEPLOYED_COMMIT` (full sha of what is live). If it is missing the script skips the ancestry
check and refuses to merge `http_app.py` unless the host copy equals the tree's.
