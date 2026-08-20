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

Tool arguments cannot override the base URL.

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

## Deliberate first-PR parity gaps

Not exposed yet (tracked for follow-up, not implied as MCP-complete):

- Node path variants: `/section/`, `/sectionid/`, `/subsection/`
- Gap analysis: `map_analysis`, `map_analysis_weak_links`, `ma_job_results`
- `GET /rest/v1/cre_csv` (binary CSV)
- `GET /rest/v1/config`
- `GET /rest/v1/health` (feature-flagged ops probe)
- Deeplink redirect routes
- `GET /rest/v1/openapi.yaml` as a tool
- `/api/capabilities`
- Authenticated MyOpenCRE / chat / admin surfaces

## Security boundary

- Fixed public GET allowlist in `application/mcp/catalog.py` — OpenAPI membership alone does **not** expose a tool
- No credentials forwarded
- No MCP bypass secret
- Callers cannot supply arbitrary methods, paths, or base URLs
- `get_node` only accepts Credoctypes for `ntype` (blocks collisions such as `/rest/v1/user/resources`)
- REST remains the backend execution and authorization boundary
