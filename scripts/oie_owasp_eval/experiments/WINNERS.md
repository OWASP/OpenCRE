# OIE experiment winners (exhaustive switch grid)

**Date:** 2026-09-22
**Worktree:** `OpenCRE-wt-oie-1088-harness`
**Shared pipeline knowledge:** `orch-exp-baseline-20260921` (Module C re-run per combo; CE on CPU; shortlist judge off — Gemini hangs blocked judge-ON factorial)
**Gold:** canonical (`local_gold: false`); Agentic stub excluded
**Grid:** 512 / 512 combos (see `tmp/oie_owasp_eval/experiments/grid/`)

## Best combo

- **id:** `g_1_0_0_0_0.85_0_0_lawrence_0`
- **score:** 27/62 (0.4355)
- **axes:** `{"cre_summary": "1", "dual_index": "0", "use_rrf": "0", "context_enrich": "0", "margin_gamma": "0.85", "hub_leaf_cage": "0", "focus_query": "0", "hybrid": "lawrence", "cre_text_enrich": "0"}`
- **env flags:** `{"CRE_LIBRARIAN_CRE_SUMMARY": "1", "CRE_LIBRARIAN_DUAL_INDEX": "0", "CRE_LIBRARIAN_USE_RRF": "0", "CRE_LIBRARIAN_CONTEXT_ENRICH": "0", "CRE_LIBRARIAN_MARGIN_GAMMA": "0.85", "CRE_LIBRARIAN_HUB_LEAF_CAGE": "0", "CRE_LIBRARIAN_FOCUS_QUERY": "0", "CRE_LIBRARIAN_HYBRID_BETA": "0", "CRE_LIBRARIAN_HYBRID_GAMMA": "0.70", "CRE_LIBRARIAN_CRE_TEXT_ENRICH": "0"}`

## Top 5

| rank | id | hits/scorable | accuracy | notes |
|---:|---|---:|---:|---|
| 1 | `g_1_0_0_0_0.85_0_0_lawrence_0` | 27/62 | 0.4355 | — |
| 2 | `g_1_0_0_0_0.85_0_0_lawrence_1` | 27/62 | 0.4355 | — |
| 3 | `g_1_0_0_0_0.85_0_0_nameheavy_0` | 27/62 | 0.4355 | — |
| 4 | `g_1_0_0_0_0.85_0_0_nameheavy_1` | 27/62 | 0.4355 | — |
| 5 | `g_1_0_0_0_0.85_0_1_lawrence_0` | 27/62 | 0.4355 | — |

## Promoted stack_winners.yaml flags

```
flags:
  CRE_LIBRARIAN_CRE_SUMMARY: '1'
  CRE_LIBRARIAN_MARGIN_GAMMA: '0.85'
```

## No-ops / caveats

- `USE_RRF=1` without `DUAL_INDEX=1` is a no-op (copied from rrf=0 sibling; still in master.csv).
- ASVS5 harvest still excluded (chapter HTML OOM); not in denominator.
- Trained CE deferred — not in this grid.
- `SHORTLIST_JUDGE=0` fixed (Gemini judge hangs blocked judge-ON factorial).

## Parallel Module C (isolated DBs)

4 workers × `cre_grid_w0`…`cre_grid_w3` (~500MB TEMPLATE clones of `cre`).

```bash
WORKERS=4 scripts/oie_owasp_eval/clone_grid_worker_dbs.sh
python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py --workers 4 --clone
# re-attach aggregator if it exits while workers keep running:
python -u scripts/oie_owasp_eval/run_exhaustive_switch_grid_parallel.py --monitor-only
```

Do not write live Links from this matrix.
