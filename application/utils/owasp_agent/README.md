# OWASP metadata agent (experimental)

Feature-flagged chat/MCP extension that answers **OWASP community / logistics**
questions from a **separate SQLite index** (Nest + GitHub), without writing into
the CRE / standards graph.

Stacked PRs: [#1125](https://github.com/OWASP/OpenCRE/pull/1125) (agent +
isolation), [#1127](https://github.com/OWASP/OpenCRE/pull/1127) (probe-gap
fixes + synth suite fixtures).

## How this relates to OIE

**OIE** (OWASP Graph / “pane of glass”) is the living-knowledge pipeline:

```text
Module A (harvest) → Module B (filter) → Module C (Librarian) → Module D (HITL)
```

See [`docs/owasp-graph/README.md`](../../../docs/owasp-graph/README.md).

**This agent is not Modules A–D.** It does not harvest standards into CREs and
does not require a running OIE pipeline. It is an experimental **OIE-adjacent**
surface for the same product goal (“ask OpenCRE about OWASP”) but for
**metadata**: chapters, events, board history, membership pricing, project
lists, fail-closed talk claims.

| Concern | OIE pipeline (A–D) | This agent |
| --- | --- | --- |
| Data | Chunks → knowledge queue → CRE links | Nest/GitHub → `OWASP_AGENT_DB` SQLite |
| Questions | Normative AppSec / CRE mapping | Community logistics / meta |
| Chat path | CRE RAG via `PromptHandler` + LLM | Rule router; LLM only on CRE fallthrough |
| Graph pollution | Writes reviewable CRE proposals | **Never** writes Credoctypes / embeddings |

When the router classifies a prompt as `cre_normative`, it returns `None` and
`/rest/v1/completion` falls through to normal CRE RAG (that path **does** need
LLM keys and a populated OpenCRE DB). Meta questions that the agent handles
never invent Nest/GitHub facts and never dump meta hits into the CRE citation
`table`.

## Architecture (runtime)

```text
User / MCP
    │
    ├─ Chat POST /rest/v1/completion   (login required)
    │       └─ if OWASP_AGENT_ENABLED:
    │             OwaspAgentRouter.handle(prompt)
    │               ├─ meta intent  → IndexStore (SQLite) → answer
    │               └─ cre_normative → None → PromptHandler (LLM + CRE RAG)
    │
    └─ MCP stdio  owasp_meta_* tools   (same flag + same index)
```

Code: `application/utils/owasp_agent/`, hook in
`application/web/web_main.py`, MCP in `application/mcp/owasp_agent_tools.py`.

## Setup (for now)

### 1. Repo + venv

```bash
git clone https://github.com/OWASP/OpenCRE.git
cd OpenCRE
# use this PR branch while #1127 is open:
# git fetch origin fix/owasp-agent-probe-gaps && git checkout fix/owasp-agent-probe-gaps
python3 -m venv venv
source venv/bin/activate
make install-python   # or: pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Environment variables

| Variable | Required for | Notes |
| --- | --- | --- |
| `OWASP_AGENT_ENABLED=1` | Agent + MCP meta tools | Off by default |
| `OWASP_AGENT_DB` | Index path | Default: `./tmp/owasp_agent.sqlite` |
| `NEST_API_KEY` | Nest sync (chapters/events/projects) | From [nest.owasp.org](https://nest.owasp.org) while logged in |
| `NEST_API_BASE` | Nest sync | Default `https://nest.owasp.org/api/v0` |
| `GITHUB_TOKEN` | GitHub sync / board-history crawl | Optional but raises rate limits; board YAML needs GitHub |
| `OWASP_AGENT_CRAWL_REPOS=1` | Extra GitHub chapter/project markdown crawl | Optional; slower |
| `GEMINI_API_KEY` | CRE RAG / chat fallthrough | LiteLLM `gemini/…` models (default chat model) |
| `OPENAI_API_KEY` | Alternate LLM provider | Only if you set `CRE_LLM_CHAT_MODEL` / embed models to `openai/…` |
| `CRE_LLM_CHAT_MODEL` | Chat fallthrough model | Default `gemini/gemini-2.5-flash` |
| `CRE_LLM_EMBED_MODEL` | Embeddings (full OpenCRE chat) | Needed for rich CRE RAG, not for agent-path synth scoring |
| `DATABASE_URL` / local Postgres | Full Flask + CRE RAG | Agent-path synth eval does **not** need Postgres |

**Agent-path synth scoring** (default): needs a synced `OWASP_AGENT_DB` only.
Nominatim geocoding for suburbs uses the public API (no key); process-local
cache applies.

**Full chat in the browser** (`/rest/v1/completion` after login): enable the
agent **and** configure LLM keys for CRE fallthrough, plus a normal OpenCRE DB
if you want normative answers.

Do not commit `.env`. Example for a laptop agent-only workflow:

```bash
export OWASP_AGENT_ENABLED=1
export OWASP_AGENT_DB="$PWD/tmp/owasp_agent.sqlite"
export NEST_API_KEY=…          # recommended
export GITHUB_TOKEN=…          # recommended
# optional for CRE fallthrough / OWASP_SYNTH_FULL=1:
export GEMINI_API_KEY=…
# export CRE_LLM_CHAT_MODEL=gemini/gemini-2.5-flash
```

### 3. Build the metadata index

```bash
mkdir -p tmp
export OWASP_AGENT_DB="$PWD/tmp/owasp_agent.sqlite"
export OWASP_AGENT_ENABLED=1
# Nest and/or GitHub — at least one should succeed
make owasp-agent-sync OWASP_AGENT_SYNC_ARGS="--db $OWASP_AGENT_DB --auto-concepts"
# GitHub-only (if Nest key missing):
# make owasp-agent-sync OWASP_AGENT_SYNC_ARGS="--db $OWASP_AGENT_DB --skip-nest --auto-concepts"
```

Without Nest, chapter/event coverage is thin and synth pass rate will drop.
Membership country discounts are seeded from the OWASP site countries list
during sync when Nest/site sources provide them.

### 4. Smoke the router (no Flask)

```bash
OWASP_AGENT_ENABLED=1 OWASP_AGENT_DB="$PWD/tmp/owasp_agent.sqlite" \
PYTHONPATH=. python - <<'PY'
from application.utils.owasp_agent import OwaspAgentRouter
print(OwaspAgentRouter().handle("How much is OWASP membership in Morocco?"))
PY
```

### 5. Optional: Flask chat + MCP

```bash
# Normal OpenCRE local stack if you want CRE RAG fallthrough:
# make docker-postgres && make migrate-upgrade
export OWASP_AGENT_ENABLED=1
export OWASP_AGENT_DB="$PWD/tmp/owasp_agent.sqlite"
export GEMINI_API_KEY=…   # for CRE fallthrough
make dev-flask            # http://127.0.0.1:5000 — completion is login_required

# MCP meta tools (same flag + DB):
python -m application.mcp
```

## Tests

### Unit tests (offline fixtures, no Nest/LLM)

```bash
OWASP_AGENT_ENABLED=1 PYTHONPATH=. \
  python -m unittest discover -s application/tests/owasp_agent -p '*_test.py'
```

### Synth suite v2 (400 unique probes)

Fixtures (this PR):

- [`application/tests/owasp_agent/fixtures/owasp_agent_synth_v2_questions.txt`](../../tests/owasp_agent/fixtures/owasp_agent_synth_v2_questions.txt) — readable questions
- [`application/tests/owasp_agent/fixtures/owasp_agent_synth_v2.jsonl`](../../tests/owasp_agent/fixtures/owasp_agent_synth_v2.jsonl) — questions + score predicates

Score against a **synced** index (agent-path; no LLM by default):

```bash
export OWASP_AGENT_ENABLED=1
export OWASP_AGENT_DB="$PWD/tmp/owasp_agent.sqlite"
make owasp-agent-synth-eval
# or:
PYTHONPATH=. python scripts/owasp_agent_synth_eval.py
```

| Env | Default | Meaning |
| --- | --- | --- |
| `OWASP_SYNTH_SUITE` | fixture JSONL above | Probe file |
| `OWASP_SYNTH_OUT` | `tmp/owasp_agent_synth_results_v2.json` | Results JSON |
| `OWASP_SYNTH_PASS_RATE` | `0.90` | Exit 0 threshold |
| `OWASP_SYNTH_FULL=1` | off | Also hit `/rest/v1/completion` for `path=completion` probes (needs running app + login-capable setup + LLM) |

Success: `pass_rate >= 0.90` and `halluc_invent == 0`. Print `SUMMARY` from the
script stdout or the `summary` key in the results JSON.

**Do not** regenerate the suite unless you intentionally change predicates
(there is no public regenerator in-tree; the checked-in JSONL is the suite).

## Isolation rules (do not break)

- Data only in `OWASP_AGENT_DB` — never CRE / Node / embeddings tables.
- Never expose meta entities via CRE REST (`tags`, `text_search`, standards, graph UI).
- Chat responses keep CRE `table` citations empty for meta answers.
- Reachable only from chat completion (flag on) and MCP `owasp_meta_*`.

## Related Makefile targets

| Target | Purpose |
| --- | --- |
| `make owasp-agent-sync` | Nest/GitHub → SQLite index |
| `make owasp-agent-merge-concepts` | Merge near-duplicate auto concepts |
| `make owasp-agent-synth-eval` | Score synth v2 JSONL against the index |
