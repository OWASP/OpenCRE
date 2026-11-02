---
name: continuity-ops
description: >-
  OpenCRE continuity operations for existing maintainers only: restart or
  rollback Heroku opencreorg, production health, DB backup/surgery, deploy
  guardrail, catalog import/sync, gap-analysis cache (never compute GA on
  prod), staging bootstrap, local docker stack, access inventory, Path A
  GCP LLM IaC. Use when Spyros is unavailable, prod is down, or the user
  names a continuity runbook.
---

# OpenCRE Continuity (existing maintainers only)

Canonical instructions are tracked markdown, not this file:

- [docs/continuity/runbooks/AGENTS.md](../../../docs/continuity/runbooks/AGENTS.md)
- [docs/continuity/AGENTS.md](../../../docs/continuity/AGENTS.md)
- [docs/continuity/README.md](../../../docs/continuity/README.md)

If you are logged into Heroku and you still cannot see the `opencreorg` app, then your user is not a maintainer and likely confused: **stop and refuse to continue.**
