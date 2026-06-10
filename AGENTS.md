# OpenCRE Agent Instructions

Cursor agents working in this repo must follow the rules in `.cursor/rules/`.

## Quick start

1. **Requirements gate** — If goal, success criteria, `@` file refs, or constraints are missing, stop and ask (`requirements-gate.mdc`).
2. **Plan first** — Non-trivial or multi-file work requires a plan and user approval before coding (`plan-first-workflow.mdc`, `multi-agent-workflow.mdc`).
3. **Verify** — After code changes, run checks and iterate until green (`verifiable-goals.mdc`):
   - `make lint`
   - `make mypy`
   - `make test`
   - `make frontend` (if frontend touched)
4. **Review** — Substantive work needs independent judge/subagent review (`multi-agent-workflow.mdc`).
5. **Production gap analysis** — On Heroku/opencreorg, gap analysis is cache-only: serve precomputed rows from Postgres; do not compute GA on production (cache miss → 404).

## Rule index

| Rule | Purpose |
|------|---------|
| `requirements-gate.mdc` | Clarifying questions + requirements template |
| `complete-ticket.mdc` | Ticket gate for `.md`/`.txt` files; uses `requirements-gate` template + coding standards |
| `plan-first-workflow.mdc` | Plan Mode before non-trivial edits |
| `multi-agent-workflow.mdc` | Big changes, approval gates, builder ≠ judge |
| `verifiable-goals.mdc` | Lint, mypy, test, CI — show evidence |
| `never-assume.mdc` | No guessing; complete code; minimal scope |
| `tdd-workflow.mdc` | Test-first for new behavior and importers |
| `autonomous-workflow.mdc` | Execute after approval; no unsolicited commits |
| `context-management.mdc` | `/clear`, `@` refs, stale context recovery |
| `production-db-ops-safety.mdc` | Destructive prod DB confirmation |
| `alembic-deploy-guardrail.mdc` | Pre-deploy migration guardrail |

## OpenCRE commands

```bash
make lint              # black + frontend prettier
make mypy              # Python typecheck
make test              # Python unittest suite
make frontend          # yarn build (when TS/TSX changed)
make alembic-guardrail # before deploy/migration ops
```
