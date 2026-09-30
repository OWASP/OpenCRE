# Feature flags (promoted)

Environment variables for Module C live under the `CRE_LIBRARIAN_*` prefix
(loader: `application/utils/librarian/config_loader.py`). This page lists what
**shipped evaluation** / `run_full_pipeline.py` uses. Flags that were tried and
did not improve the product metrics are documented in
[experimental-feature-flags.md](experimental-feature-flags.md).

## Promoted stack (d1-winner + post-60)

| Variable | Value | Why |
|----------|-------|-----|
| `CRE_LIBRARIAN_CRE_SUMMARY` | `1` | Strongest exact-bar lever in the 512-combo grid. |
| `CRE_LIBRARIAN_MARGIN_GAMMA` | `0.85` | Relative cutoff after C.2; wired in `LibrarianPipeline`. |
| `CRE_LIBRARIAN_DUAL_INDEX` | `1` (code default) | Dual header/body index; on by default in `load_config`. |
| `CRE_LIBRARIAN_SHORTLIST_JUDGE` | `1` | Grounded judge (full-pipeline `setdefault`). |
| `CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS` | `3` | Aligns judge lead with score `top_k=3`. |
| `CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP` | `8` | E5 promote cap (d1 winner). |
| `CRE_LIBRARIAN_LEAF_DRILLDOWN` | `1` | Hub→leaf after C.2; grain gate `MIN_SECTIONS=20`. |
| `CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB` | `0` | E1 off. |
| `CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST` | `0` | E2 off. |
| `CRE_LIBRARIAN_LEAF_DRILLDOWN_FORCE_RESOURCES` | unset | `api` raised GitHub d1 but dropped API exact 60→50; leave off. |

YAML (historical grid cell): `scripts/oie_owasp_eval/experiments/stack_winners.yaml`.

### Fixed defaults used with the promoted stack

| Variable | Value | Notes |
|----------|-------|-------|
| `CRE_LIBRARIAN_PRIOR_CAGE` | on | Prior-caged C.1 |
| `CRE_LIBRARIAN_PREF_INJECT` | on | Inject preferred CRE ids |
| `CRE_LIBRARIAN_PREFER_AUDIT_IDS` | on | Prefer those ids in order |
| `CRE_LIBRARIAN_HYBRID_BETA` | `0` | “Lawrence” mix |
| `CRE_LIBRARIAN_HYBRID_GAMMA` | `0.70` | Cross-encoder weight (≠ margin γ) |
| `CRE_LIBRARIAN_RETRIEVER_BACKEND` | `pgvector` | Live B2 / full-pipeline |
| `CRE_LIBRARIAN_DEVICE` | `cpu` | Eval matrix |
| `CRE_LIBRARIAN_USE_RRF` | off | See [experimental-feature-flags.md](experimental-feature-flags.md) |
| `CRE_LIBRARIAN_HUB_LEAF_CAGE` | off | See experimental notes |
| `CRE_LIBRARIAN_CONTEXT_ENRICH` | off | See experimental notes |
| `CRE_LIBRARIAN_FOCUS_QUERY` | off | Neutral / slight drag on grid mean |
| `CRE_LIBRARIAN_CRE_TEXT_ENRICH` | off | Tied at top; mean slightly lower when on |

## Headline scores (cold-start post-60, hub LLM gold)

Cold-start run `20261002T103821Z` (`tmp/oie_owasp_eval/full_pipeline_cold_start_post60/`)
used FORCE=`api` for that experiment. **Shipped default leaves FORCE unset** so API
exact stays on the ~60% lane; GitHub d1 is the product bar we optimize.

| Arm | Exact | Notes |
|-----|------:|-------|
| GitHub (ASVS/AISVS/…) | 32.2% (65/202) | d1 ≈ 59.9% on that run |
| OWASP Top 10 | ~90% | B2 arm |
| OWASP API Top 10 | 50% with FORCE=`api`; ~60% with FORCE off | Do not ship FORCE |
| OWASP LLM Top 10 (hub AI gold, #1124) | 50% | Hub-aligned gold rewrite |

Older offline rescore on prior gold (SUMMARY+margin only): 33/62 exact / 52/62
neighborhood — superseded for AIX by the hub gold + d1-winner stack above.

Neighborhood definition:
[Evaluation and metrics](evaluation-and-metrics.md).

## Reproduce

```bash
# Matches scripts/oie_owasp_eval/run_full_pipeline.py _apply_promoted_flags
export CRE_LIBRARIAN_CRE_SUMMARY=1
export CRE_LIBRARIAN_MARGIN_GAMMA=0.85
export CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector
export CRE_LIBRARIAN_SHORTLIST_JUDGE=1
export CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS=3
export CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP=8
export CRE_LIBRARIAN_LEAF_DRILLDOWN=1
export CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS=20
export CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB=0
export CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST=0
# leave CRE_LIBRARIAN_LEAF_DRILLDOWN_FORCE_RESOURCES unset
export NO_LOAD_GRAPH_DB=1

PYTHONPATH=. python scripts/oie_owasp_eval/run_full_pipeline.py \
  --cache-file "$CACHE" \
  --out tmp/oie_owasp_eval/full_pipeline_verify
```

ASVS 5 only (exclude other B2 families):

```bash
PYTHONPATH=. python scripts/oie_owasp_eval/run_b2_pr_mappings.py \
  --keep-all-knowledge \
  --exclude-fixtures \
    owasp_top10_2025 owasp_api_top10_2023 owasp_llm_top10_2025 \
    owasp_aisvs_1_0 owasp_kubernetes_top10_2025 owasp_kubernetes_top10_2022 \
  --out tmp/oie_owasp_eval/experiments/asvs5_stack_winners.b2_report.json
```

Then score neighborhood with `score_b2_hop_distance.py`.

## Open items

- Trained cross-encoder: deferred; not in the grid.
- Live Module C re-run on every gold revision still required when fixtures change;
  see [evaluation-and-metrics.md](evaluation-and-metrics.md).
