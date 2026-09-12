# Agents: GCP LLM IaC (Path A)

Existing maintainers only. Root policy: [`AGENTS.md`](../../AGENTS.md). Operator checklist: [`docs/continuity/runbooks/gcp-iac.md`](../../docs/continuity/runbooks/gcp-iac.md). Runbook skill: [`docs/continuity/runbooks/AGENTS.md`](../../docs/continuity/runbooks/AGENTS.md).

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

**The plan lives in this directory:** [`README.md`](README.md) (Path A, secrets/vars, apply steps, security model). There is no `.cursor/plans/` file for this stack.

## Do

- Path A only: Generative Language API + restricted `GEMINI_API_KEY`. LiteLLM `gemini/…`, not `vertex_ai/…`.
- New GCP project on the operator’s billing. Never import `opencre-vertex`.
- GitHub Environment `gcp-iac` for secrets/vars. Workflow: `.github/workflows/gcp-iac.yml` (`workflow_dispatch` only).
- Plan-only unless the human types `APPLY` (workflow input `confirm_apply=APPLY`).
- After first apply: set `GCP_WIF_PROVIDER`, `GCP_TF_SA_EMAIL`, `TF_STATE_BUCKET`; delete secret `GOOGLE_CREDENTIALS`.
- Local check: `make gcp-iac-validate`. Heroku PATCH helper: `scripts/gcp/patch_heroku_llm_config.py` (named keys only).

## Do not

- Log `GEMINI_API_KEY`, `GOOGLE_CREDENTIALS`, `HEROKU_API_KEY`, or `heroku config` values.
- Run `terraform apply` locally against production.
- Add this workflow to `pull_request`.
- Flip `create_project` true→false in the same state (would destroy the project).
- Enable Vertex / `aiplatform` or PATCH `VERTEX_*` Heroku vars.
