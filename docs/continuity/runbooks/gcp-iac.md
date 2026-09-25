# Continuity runbook: GCP LLM IaC

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md) and [`infra/gcp/AGENTS.md`](../../../infra/gcp/AGENTS.md)

**Path A:** Generative Language API + restricted `GEMINI_API_KEY` (LiteLLM `gemini/…`). Not Vertex.

Stand up (or replace) the Google LLM project on **the operator’s billing account**. Do not import `opencre-vertex`.

## Agent prompt

Paste into your agent:

```
Run the OpenCRE GCP IaC continuity path. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read infra/gcp/AGENTS.md, infra/gcp/README.md, docs/continuity/runbooks/AGENTS.md, and .github/workflows/gcp-iac.yml.
Do not print GitHub secrets, GOOGLE_CREDENTIALS, GEMINI_API_KEY, or heroku config values.
Do not run terraform apply locally against production.
Help me fill GitHub Environment gcp-iac secrets/vars and run the workflow plan-only first.
confirm_apply=APPLY only when I type APPLY in chat.
```

## Done when

- Plan workflow is green
- APPLY has run once, WIF vars + `TF_STATE_BUCKET` are set, `GOOGLE_CREDENTIALS` deleted
- Chatbot health still 401 unauthenticated (`make monitor-chatbot-health-prod`)
