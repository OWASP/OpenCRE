# Phase 0 — Worktree Hygiene Inventory

> Inventory only. Cloud agents must **not** mass-delete local worktrees.

**Goal:** Record which git worktrees / experimental branches relate to RAG/OIE parity so humans can keep, merge, or delete them locally.

**Architecture:** Markdown inventory committed on the parity PR branch. No automation that prunes worktrees remotely.

## Inventory (cloud checkout)

| Path / ref | Role | Recommendation |
|---|---|---|
| `cursor/phase-1-cre-descriptions-2bbe` (this PR #1200) | Phases 1–7 parity implementation | **Keep / merge** into `staging` after review |
| `staging` | Integration base | **Keep** |
| `main` / `master` | Default / release | **Keep** — do not push parity WIP here |
| Local `cre_summary` / OIE experiment branches (homeserver) | Steal ideas only; not product modules | **Merge useful ideas** then delete local worktrees after cherry-pick |
| `tmp/oie_*` caches | Eval artifacts | **Keep locally**; already gitignored |

## Rules

- Do not `git worktree remove` from cloud against developer machines.
- Prefer one PR (`#1200`) for the parity stack; do not open parallel PRs for Phases 2–7.
- After merge: human deletes obsolete local worktrees with `git worktree list` + `git worktree remove`.
