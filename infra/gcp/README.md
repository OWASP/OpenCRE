# OpenCRE GCP IaC (continuity) — Path A

This file **is** the IaC plan (Path A, secrets, apply, security). Agents: [`AGENTS.md`](AGENTS.md). Runbook: [`docs/continuity/runbooks/gcp-iac.md`](../../docs/continuity/runbooks/gcp-iac.md).

**Path A only:** Google AI Studio / Generative Language API + a restricted `GEMINI_API_KEY`. LiteLLM models stay `gemini/…` (not `vertex_ai/…`). No Vertex service account, no OAuth login stack.

Terraform **creates a new GCP project** on whoever’s billing account, enables `generativelanguage.googleapis.com`, mints the key, and GitHub Actions **PATCHes only those Heroku LLM vars**. Spyros’s personal `opencre-vertex` is never imported. OAuth remains off (`NO_LOGIN=1`).

## Security model

| Control | How |
|---|---|
| No keys in git | State in a private GCS bucket (`public_access_prevention=enforced`, UBLA, versioning) |
| No apply on PRs | `workflow_dispatch` only, workflow name `GCP IaC` |
| Human gate | Type `APPLY` to apply; anything else is plan-only |
| Environment | GitHub Environment `gcp-iac` (required reviewers + secrets) |
| After bootstrap | GitHub OIDC → Workload Identity Federation (delete `GOOGLE_CREDENTIALS`) |
| OIDC lock | Repo `OWASP/OpenCRE`, `refs/heads/main`, environment `gcp-iac`, this workflow only |
| Actions | Pinned to commit SHAs; `persist-credentials: false`; `terraform_wrapper: false` |
| Heroku | Platform API PATCH of named keys only (does not wipe other config). Key values never logged |
| Project | `deletion_policy = PREVENT` + `prevent_destroy` on project, state bucket, API key |

Do **not** add this workflow to `pull_request`. A fork PR with OIDC would be a privilege path; it is not enabled.

## GitHub Environment `gcp-iac`

Create once (Settings → Environments → New: `gcp-iac`). Restrict to branch `main`. Add required reviewers (Spyros + Rob).

### Secrets

| Secret | Purpose |
|---|---|
| `GCP_BILLING_ACCOUNT_ID` | `XXXXXX-XXXXXX-XXXXXX` |
| `GOOGLE_CREDENTIALS` | **Bootstrap only.** JSON of a user/SA that can create a project on that billing account (`billing.user` + `resourcemanager.projectCreator`). Delete after WIF vars are set |
| `HEROKU_API_KEY` | Same class of key as environment `opencreorg`; used only to PATCH LLM config vars |

### Variables

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | globally unique id, e.g. `opencre-llm-prod` |
| `GCP_REGION` | `us-central1` |
| `HEROKU_APP` | `opencreorg` |
| `GCP_BUDGET_USD` | `50` |
| `GCP_ORG_ID` | optional, empty for personal billing |
| `GCP_FOLDER_ID` | optional |
| `GCP_WIF_PROVIDER` | fill after first apply (`terraform output -raw wif_provider`) |
| `GCP_TF_SA_EMAIL` | fill after first apply |
| `TF_STATE_BUCKET` | fill after first apply (`opencre-tfstate-<project_id>`) |

## Run

1. Environment + secrets/vars above (except WIF / bucket).
2. Actions → **GCP IaC** → Run workflow → leave confirm empty → read the plan.
3. Run again with `confirm_apply=APPLY`.
4. Copy job log lines `GCP_WIF_PROVIDER`, `GCP_TF_SA_EMAIL`, `TF_STATE_BUCKET` into environment variables.
5. Delete secret `GOOGLE_CREDENTIALS`.
6. Later applies use OIDC only.

`make gcp-iac-validate` locally (fmt + init -backend=false + validate). No Google credentials required.

## Bus-factor (Rob)

Create a GCP billing account, put **his** billing id and (once) a bootstrap JSON into `gcp-iac`, set a new `GCP_PROJECT_ID`, APPLY. Do not try to take over `opencre-vertex`.
