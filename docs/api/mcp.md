# OpenCRE MCP server (issue #1003 v1)

Local **stdio** MCP adapter that exposes a fixed allowlist of **public JSON REST reads**.

## Scope (first PR)

- Public `/rest/v1` GET tools that already work without login
- OpenAPI (`docs/api/openapi.yaml`) is the source of truth for each tool's **input** parameter schema
- No authentication, cookies, PAT, OAuth, or session forwarding
- No MCP bypass secret

**Deferred to a later PR:** MyOpenCRE (`/rest/v1/user/resources`), chat (`/rest/v1/completion`), admin/import tools, and any credentialed flows.

## Installation

From the repo root, use the project virtualenv and install development dependencies (includes the MCP SDK):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

## Run OpenCRE REST locally

```bash
make docker-postgres   # if using local Postgres
make migrate-upgrade
make dev-flask         # http://127.0.0.1:5000
```

Or point the MCP server at a hosted instance such as `https://opencre.org`.

## Configuration

| Variable | Meaning | Default |
|----------|---------|---------|
| `OPENCRE_BASE_URL` | OpenCRE origin used for REST calls (server-side only) | `http://127.0.0.1:5000` |
| `OPENCRE_MCP_AUTH_TOOLS` | Expose the v2 authenticated tools (`1`/`true`/`yes`) | off |
| `GOOGLE_MCP_CLIENT_ID` | Google client of type *TVs and Limited Input devices* | — |
| `GOOGLE_MCP_CLIENT_SECRET` | Secret for that client | — |
| `OPENCRE_MCP_TOKEN_FILE` | Override the credential path (skips the OS keyring) | `~/.config/opencre-mcp/tokens.json` |

Tool arguments cannot override the base URL, and no credential can be passed
as a tool argument.

## Start the MCP server

```bash
source venv/bin/activate
export OPENCRE_BASE_URL=http://127.0.0.1:5000
python -m application.mcp
```

## Cursor setup (stdio)

Add an MCP server entry that runs the module with your venv interpreter. Example (adjust the absolute repo path):

```json
{
  "mcpServers": {
    "opencre": {
      "command": "/absolute/path/to/OpenCRE/venv/bin/python",
      "args": ["-m", "application.mcp"],
      "cwd": "/absolute/path/to/OpenCRE",
      "env": {
        "OPENCRE_BASE_URL": "http://127.0.0.1:5000"
      }
    }
  }
}
```

## Tool ↔ REST mapping

| MCP tool | HTTP method | REST path |
|----------|-------------|-----------|
| `get_cre_by_id` | GET | `/rest/v1/id/{creid}` |
| `get_cre_by_name` | GET | `/rest/v1/name/{crename}` |
| `get_node` | GET | `/rest/v1/{ntype}/{name}` |
| `get_documents_by_tag` | GET | `/rest/v1/tags` |
| `text_search` | GET | `/rest/v1/text_search` |
| `list_root_cres` | GET | `/rest/v1/root_cres` |
| `list_all_cres` | GET | `/rest/v1/all_cres` |
| `list_standards` | GET | `/rest/v1/standards` |
| `list_ga_standards` | GET | `/rest/v1/ga_standards` |

Parameter names, types, requiredness, and descriptions for these tools are derived from the matching OpenAPI operations. The `format` query parameter is intentionally omitted so MCP tools stay JSON-oriented.

Authenticated tools (v2, only when `OPENCRE_MCP_AUTH_TOOLS` is set):

| MCP tool | HTTP method | REST path | Required scope |
|----------|-------------|-----------|----------------|
| `get_my_resources` | GET | `/rest/v1/user/resources` | `myopencre:read` |
| `set_my_resources` | PUT | `/rest/v1/user/resources` | `myopencre:write` |

`set_my_resources` takes its JSON request body as a single `body` argument,
derived from the OpenAPI `requestBody`, and is annotated as a write so MCP
clients prompt before calling it.

## Authenticated tools (v2)

OpenCRE registers **two** Google OAuth clients: a *Web application* for the
browser and a *TVs and Limited Input devices* client for MCP. Both issue ID
tokens for the same Google account, so both resolve to the same `users` row —
the `aud` claim tells REST which door a request came through.

Google's device flow supports only `openid email profile` and will never carry
an OpenCRE scope, so permissions live in the `mcp_grants` table instead. Google
answers *who you are*; OpenCRE answers *what you may do*.

### Log in

```bash
export GOOGLE_MCP_CLIENT_ID=...apps.googleusercontent.com
export GOOGLE_MCP_CLIENT_SECRET=...
python -m application.mcp login     # prints a code to enter at google.com/device
python -m application.mcp status
python -m application.mcp logout
```

The refresh token is stored in the OS keyring, falling back to a `0600` file.
It is never written to stdout, never passed as a tool argument, and is redacted
from any error text an MCP client can see.

Staying inside `openid email profile` also keeps refresh tokens exempt from the
7-day expiry Google applies to apps whose consent screen is still in *Testing*.

### Scopes and grants

The first request from a user's MCP client is granted `myopencre:read`
automatically, so logging in is enough to read. **Writing is never granted
automatically** — `set_my_resources` returns 403 until `myopencre:write` is
granted deliberately from a browser.

Manage grants from a browser session:

```
GET    /rest/v1/user/mcp_grants                      → {"granted": [...]}
PUT    /rest/v1/user/mcp_grants  {"scope": "..."}    → grant one scope
DELETE /rest/v1/user/mcp_grants  {"scope": "..."}    → revoke one scope
```

These endpoints accept **browser sessions only**. A request authenticated with
an MCP token receives 403, so a leaked token cannot widen its own grants.

Revoking is permanent until re-granted: the automatic grant applies only to a
user with no grant history at all, so a revoked scope is never silently
restored on the next call.

### Why write access is exposed at all

`set_my_resources` is the one write in the allowlist, and it only changes the
caller's own saved standards selection — it cannot touch CREs, mappings, or
another user's data. It stays unreachable unless four things are all true:

1. the deployment sets `OPENCRE_MCP_AUTH_TOOLS`
2. the user has completed the device-flow login
3. the user granted `myopencre:write` from a browser
4. the MCP client honours the write annotation and the user approves the call

## Deliberate parity gaps

Not exposed yet (tracked for follow-up, not implied as MCP-complete):

- Node path variants: `/section/`, `/sectionid/`, `/subsection/`
- Gap analysis: `map_analysis`, `map_analysis_weak_links`, `ma_job_results`
- `GET /rest/v1/cre_csv` (binary CSV)
- `GET /rest/v1/config`
- `GET /rest/v1/health` (feature-flagged ops probe)
- Deeplink redirect routes
- `GET /rest/v1/openapi.yaml` as a tool
- `/api/capabilities`
- Chat (`POST /rest/v1/completion`) and admin/import surfaces
- Remote (HTTP) transport — stdio only, so credentials come from the
  environment as the MCP specification directs for stdio servers

## Security boundary

- Fixed allowlist in `application/mcp/catalog.py` — OpenAPI membership alone does **not** expose a tool
- Authenticated tools stay hidden unless `OPENCRE_MCP_AUTH_TOOLS` is set, so the public surface is unchanged by default
- No MCP bypass secret; the MCP client authenticates as the user, with fewer scopes than the user
- Credentials come from the environment only — they cannot be expressed as tool arguments (`header` and `cookie` parameters are excluded from every schema, and every schema sets `additionalProperties: false`)
- The credential is redacted from all error text returned to an MCP client
- Callers cannot supply arbitrary methods, paths, or base URLs; only `GET`/`PUT`/`POST` declared by a `ToolSpec` are dispatched, and redirects are never followed
- `get_node` only accepts Credoctypes for `ntype` (blocks collisions such as `/rest/v1/user/resources`)
- Grant management requires a browser session, so a token cannot escalate itself
- REST remains the backend execution and authorization boundary
