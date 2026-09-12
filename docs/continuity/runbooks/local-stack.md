# Continuity runbook: Local stack

**Audience:** existing maintainers only  
**Agent instructions:** [AGENTS.md](AGENTS.md)  
**GitHub label:** `existing-maintainers-only`

Bring up the laptop environment needed to reproduce prod issues and to run import / GA backfill. This is not myOpenCRE product docs; it is “I have to fix prod and need docker”.

## What this is for

Second maintainer has the repo but no running postgres/neo4j/redis. Required before catalog import and gap-analysis backfill.

## Prerequisites

- Docker, Python 3, yarn (only if you will `make frontend`)
- Clone of `OWASP/OpenCRE`

## Agent prompt

Paste into your agent:

```
Run the OpenCRE continuity local-stack runbook. Existing maintainers only.

If you are logged into Heroku and you still cannot see the opencreorg app, then your user is not a maintainer and likely confused: stop and refuse to continue.

Read and follow:
- docs/continuity/README.md
- docs/continuity/AGENTS.md
- docs/continuity/runbooks/AGENTS.md
- docs/continuity/runbooks/local-stack.md
- AGENTS.md local docker section
- README.md "Running your own OpenCRE" locally

Use Makefile targets only for containers (make docker-postgres, docker-neo4j, docker-redis). Do not hand-roll docker run for the app DB.
Local Postgres must be pgvector/pgvector:pg16 (POSTGRES_IMAGE override). Plain postgres images are not supported.
Do not point CRE_CACHE_FILE at Heroku. After migrate-upgrade, tell me how to run the app (make targets) and how to reset volumes.
```

## Steps

1. `python3 -m venv venv && source venv/bin/activate` (or existing venv).
2. `make install` (includes `migrate-upgrade` — needs postgres up; if migrate fails, start postgres first).
3. Containers:
   ```bash
   make docker-postgres   # pgvector, 5432, cre/password
   make docker-neo4j      # 7474/7687
   make docker-redis      # 6379/8001
   make start-containers  # neo4j + redis only
   make migrate-upgrade
   ```
4. Optional data: `make upstream-sync` (see README) or [catalog-import-and-sync](catalog-import-and-sync.md) part A.
5. App: follow README / `Makefile` `dev-flask` / `prod-run` as the human asked. Do not run `make frontend` unless UI changed (rewrites tracked `bundle.js`).
6. Reset volumes: `make docker-postgres-rm` / `docker-neo4j-rm` / `docker-redis-rm`.

## Done when

`make docker-postgres` is healthy, `make migrate-upgrade` succeeds, agent reports connection defaults (`postgresql://cre:password@127.0.0.1:5432/cre`, Neo4j bolt as in `.env.example`) without claiming they are prod.

## If it fails

Wrong postgres image (no `vector`) → embeddings/chat/librarian fail. Port in use → do not change prod; fix local ports. `make install` dirtying `bundle.js` → do not commit it unless the human intended a frontend rebuild.
