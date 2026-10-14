# Homeserver staging (`staging.opencre.org`)

**Runtime:** dedicated **Docker Compose stack** for OpenCRE staging — own Postgres (pgvector), Redis, web, OIE workers, and `cloudflared`.  
**Not** inside the Cursor `my-agents` worker process. `my-agents` may only *bootstrap* the stack on the homeserver; the long-running system is Compose.

Internet entry: **Cloudflare Tunnel only** → Compose `web:5001` (Flask) and `mcp:5002` (Streamable HTTP MCP) on an internal Docker network (or host loopback published only to the tunnel container).

Login: Google + `LOGIN_ALLOWED_EMAILS` (Spyros / Rob / Rock only).

---

## Cloudflare (already applied)

- Tunnel: `opencre-staging`
- Ingress (path order matters — more specific first):
  - `staging.opencre.org/mcp*` → `http://127.0.0.1:5002` (Compose `mcp` / Streamable HTTP)
  - `staging.opencre.org` → `http://127.0.0.1:5001` (Compose `web`)
- DNS: `staging.opencre.org` → `{tunnel_id}.cfargotunnel.com` (proxied)
- Connector token: operator machine `/tmp/opencre_staging_tunnel_token` — copy into Compose secrets; **never commit**

Homeserver ops after deploy: update the tunnel ingress for `/mcp*`, rebuild Compose (`mcp` service), mint an Admin API JWT on staging, then verify Cursor `url: https://staging.opencre.org/mcp`.

---

## Compose layout (`deploy/staging/`)

```text
deploy/staging/
  docker-compose.yml
  .env.example          # no secrets — copy to .env on the host
```

| Service | Role | Notes |
|---------|------|--------|
| `db` | `pgvector/pgvector:pg16` | Volume `opencre_staging_pg`; **not** shared with laptop/dev Postgres |
| `redis` | Redis Stack | Volume `opencre_staging_redis`; queue `oie` |
| `web` | gunicorn/Flask | Bind internal; tunnel reaches `:5001` |
| `mcp` | uvicorn Streamable HTTP | `OPENCRE_MCP_REMOTE=1`; tunnel `/mcp*` → `:5002`; public tools open, remote `ask` needs Admin JWT |
| `worker` | `cre.py --start_worker` ×N | Same image as web; **must** set `CRE_WORKER_QUEUES=oie,default` (default listen has no `oie`) |
| `ga-worker` | profile `ga` | Optional; `CRE_WORKER_QUEUES=ga` when `CRE_OIE_GA_VIA_QUEUE=1` |
| `cloudflared` | Tunnel connector | Token from Docker secret / env file on host |
| (optional) `neo4j` | Only if staging needs Neo/GA compute | Prefer cache-only like prod |

Network: private bridge `opencre_staging_net`. **No** publishing Postgres/Redis to the public interface. Prefer publishing web/mcp as `127.0.0.1:5001:5001` and `127.0.0.1:5002:5002` so only cloudflared (host or sidecar) can reach them.

---

## Env (host file / Compose `env_file`, not git)

```bash
NO_LOGIN=0
CRE_ENABLE_LOGIN=1
LOGIN_ALLOWED_DOMAINS=*
LOGIN_ALLOWED_EMAILS=spyros.gasteratos@owasp.org,rob.van.der.veer@owasp.org,rock.lambros@owasp.org
# Google OAuth redirect: https://staging.opencre.org/rest/v1/auth/callback
GOOGLE_CLIENT_ID=…
GOOGLE_CLIENT_SECRET=…
DATABASE_URL=postgresql://cre:…@db:5432/cre
DEV_DATABASE_URL=postgresql://cre:…@db:5432/cre
REDIS_URL=…   # as app expects
NEST_API_KEY=…
GEMINI_API_KEY=…
OWASP_AGENT_ENABLED=1
OWASP_AGENT_DB=postgresql://cre:…@db:5432/cre   # agent index in same DB or separate schema
CRE_ALLOW_IMPORT=1
CRE_OIE_GA_VIA_QUEUE=1   # scheduled GA enqueues on ``ga``; never compute on Heroku
# Optional dedicated GA workers: CRE_WORKER_QUEUES=ga
TUNNEL_TOKEN=…   # cloudflared only
```

**Heroku `opencreorg` is out of scope for this stack’s live path:** no `--run_scheduled`,
no `oie` on `CRE_WORKER_QUEUES`, gap analysis is cache-only (see `docs/oie/feature-flags.md`).

---

## Bring-up (homeserver preferred; Colima laptop OK short-term)

```bash
cd /path/to/OpenCRE
git fetch && git checkout feat/oie-rq-fanout && git pull
cd deploy/staging
cp .env.example .env   # fill GOOGLE_*, GEMINI_*, NEST_*, POSTGRES_PASSWORD, TUNNEL_TOKEN
docker compose up -d --build
# cloudflared: on Linux use `docker compose --profile tunnel up -d`
# on macOS/Colima run host: cloudflared tunnel run --token "$TUNNEL_TOKEN"
# optional catalog seed (skips by default via CRE_SKIP_UPSTREAM_SYNC=1):
#   docker compose exec -e CRE_SKIP_UPSTREAM_SYNC=0 web python /code/cre.py --upstream_sync
```

---

## Verify

```bash
curl -sI https://staging.opencre.org | head -5
curl -i https://staging.opencre.org/mcp | head -20   # MCP/HTTP, not Flask 404 HTML
docker compose -f deploy/staging/docker-compose.yml ps
# Allowlisted Google → login OK; other Google → 403
# Remote ask: Bearer Admin API JWT required; public MCP tools work without it
```

---

## Relation to my-agents

| Role | Who |
|------|-----|
| Long-running OpenCRE staging | **Compose stack** (this doc) |
| One-shot “bring the stack up / fix tunnel” | Optional Cursor **my-agents** job on the homeserver |
| Laptop Cursor chat | Code + Cloudflare DNS/API; not the runtime |
