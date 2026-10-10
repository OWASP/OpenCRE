# Homeserver staging (`staging.opencre.org`)

Internet entry is **Cloudflare Tunnel only** → `127.0.0.1:5001`.  
Login allowlist (Google): three OWASP emails via `LOGIN_ALLOWED_EMAILS`.

## Cloudflare (already applied from laptop)

- Tunnel name: `opencre-staging`
- Ingress: `staging.opencre.org` → `http://127.0.0.1:5001`
- DNS: `staging.opencre.org` CNAME → `{tunnel_id}.cfargotunnel.com` (proxied)
- Connector token: on operator machine as `/tmp/opencre_staging_tunnel_token` (mode 600) — copy to homeserver; **do not commit**

## Homeserver env (not in git)

```bash
export NO_LOGIN=0
export CRE_ENABLE_LOGIN=1
export LOGIN_ALLOWED_DOMAINS='*'
export LOGIN_ALLOWED_EMAILS='spyros.gasteratos@owasp.org,rob.van.der.veer@owasp.org,rock.lambros@owasp.org'
# Google OAuth: authorized redirect
#   https://staging.opencre.org/rest/v1/auth/callback
export GOOGLE_CLIENT_ID=…
export GOOGLE_CLIENT_SECRET=…
export NEST_API_KEY=…
export GEMINI_API_KEY=…   # or Vertex
export OWASP_AGENT_ENABLED=1
export OWASP_AGENT_DB=postgresql://…   # or sqlite path
export CRE_ALLOW_IMPORT=1
export INSECURE_REQUESTS=   # unset — HTTPS at Cloudflare
export DEV_DATABASE_URL=postgresql://cre:password@127.0.0.1:5432/cre
```

Bind Flask/gunicorn to **`127.0.0.1:5001` only**.

## cloudflared

```bash
# token from /tmp/opencre_staging_tunnel_token (operator copy)
cloudflared service install "$TUNNEL_TOKEN"
# or: cloudflared tunnel run --token "$TUNNEL_TOKEN"
```

## App stack

```bash
git fetch && git checkout feat/oie-rq-fanout && git pull
make start-containers
make migrate-upgrade   # if needed
make start-oie-workers
# run web on 127.0.0.1:5001 with env above
```

## Verify

```bash
curl -sI https://staging.opencre.org | head -5
# Allowlisted Google login → /admin OK
# Other Google account → login 403
```
