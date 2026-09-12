# Agents: GCP → Heroku LLM config

Existing maintainers only. Called from GitHub Actions `GCP IaC` after Terraform apply. Plan: [`infra/gcp/README.md`](../../infra/gcp/README.md). Agent file: [`infra/gcp/AGENTS.md`](../../infra/gcp/AGENTS.md).

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**

`patch_heroku_llm_config.py` PATCHes **named** Path A keys only (`GEMINI_API_KEY`, `GOOGLE_PROJECT_ID`, `GOOGLE_PROJECT_LOCATION`, `CRE_LLM_CHAT_MODEL`, `CRE_EMBED_MODEL`). It does not wipe other Heroku config.

## Do not

- Print `HEROKU_API_KEY`, `GEMINI_API_KEY`, or PATCH bodies.
- Add `VERTEX_*` keys or `vertex_ai/` model prefixes.
- Point `HEROKU_APP` at an unnamed app; default prod is `opencreorg`.
