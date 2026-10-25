# Replatform options (off Heroku)

Status: draft for discussion. Production keeps working as today; every feature in the comprehension stack is
behind a flag that is off by default (`OWASP_CX_*`, `OWASP_COMPREHENSION_*`, `OWASP_WARMUP`, `ANSWER_LOG_*`).

What the stack needs from a host:

| Need | Why |
|---|---|
| Postgres with the `vector` extension (pgvector 0.7+, halfvec + HNSW) | answer retrieval; `pgvector/pgvector:pg16` image |
| 1 web process + 1 MCP process (long-lived, SSE) | MCP `ask` holds connections open; Heroku's 30 s router timeout is the main friction |
| Redis (RQ queue) + N workers | ingestion and scheduled jobs |
| Neo4j | gap analysis (can stay off for answer-only deployments) |
| Outbound HTTPS to Gemini | embeddings and answers |

Options:

1. **Single VM (Hetzner/DigitalOcean/GCP) with Docker Compose** — what staging runs today (`deploy/staging`). Cheapest
   (about 20-40 USD/month for 4 vCPU/16 GB), full control of Postgres extensions, no request timeouts. Needs backups
   (`pg_dump` to object storage), TLS (the edge container), and someone on call.
2. **Managed container platform (Fly.io, Render, Railway) + managed Postgres with pgvector** — less ops, deploys from
   the same Dockerfile; check pgvector version support and the idle-connection limits for SSE. Roughly 60-150 USD/month.
3. **Kubernetes (GKE/EKS)** — only worth it if OWASP already runs a cluster; the repo has GCP IaC drafts in the open
   continuity PRs (#1090, #1091). Highest cost and ops load.

Recommendation: option 1 for the alpha (it is the proven staging setup), option 2 if nobody wants to carry the VM.
Migration steps are the same for both: restore the Heroku Postgres dump, run `make alembic-guardrail` and
`flask db upgrade`, point the DNS at the new edge, keep Heroku read-only for one week as fallback.
