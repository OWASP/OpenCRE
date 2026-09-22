# Feature flags (promoted)

Environment variables for Module C live under the `CRE_LIBRARIAN_*` prefix
(loader: `application/utils/librarian/config_loader.py`). This page lists what
**shipped evaluation** uses. Flags that were tried and did not improve the
exact Links bar are documented on branch
[`experimental-feature-flags`](https://github.com/OWASP/OpenCRE/tree/experimental-feature-flags).

## Promoted stack

| Variable | Value | Why |
|----------|-------|-----|
| `CRE_LIBRARIAN_CRE_SUMMARY` | `1` | Strongest exact-bar lever in the 512-combo grid and one-factor matrix. |
| `CRE_LIBRARIAN_MARGIN_GAMMA` | `0.85` | Relative cutoff after rerank; ties summary alone on exact, keeps multi-CRE sections without dumping the full shortlist. |

YAML: `scripts/oie_owasp_eval/experiments/stack_winners.yaml`.

### Fixed defaults used in the winning grid cells

These were held constant or selected among tied winners:

| Variable | Value | Notes |
|----------|-------|-------|
| `CRE_LIBRARIAN_PRIOR_CAGE` | on | Prior-caged C.1 |
| `CRE_LIBRARIAN_PREF_INJECT` | on | Inject preferred CRE ids |
| `CRE_LIBRARIAN_PREFER_AUDIT_IDS` | on | Prefer those ids in order |
| `CRE_LIBRARIAN_HYBRID_BETA` | `0` | “Lawrence” mix |
| `CRE_LIBRARIAN_HYBRID_GAMMA` | `0.70` | Cross-encoder weight in the hybrid mix (≠ margin γ) |
| `CRE_LIBRARIAN_RETRIEVER_BACKEND` | `pgvector` | Live B2 |
| `CRE_LIBRARIAN_DEVICE` | `cpu` | Eval matrix |
| `CRE_LIBRARIAN_SHORTLIST_JUDGE` | `0` | Gemini judge hangs blocked judge-ON factorial |
| `CRE_LIBRARIAN_DUAL_INDEX` | off | See experimental branch |
| `CRE_LIBRARIAN_USE_RRF` | off | See experimental branch |
| `CRE_LIBRARIAN_HUB_LEAF_CAGE` | off | See experimental branch |
| `CRE_LIBRARIAN_CONTEXT_ENRICH` | off | See experimental branch |
| `CRE_LIBRARIAN_FOCUS_QUERY` | off | Neutral / slight drag on grid mean |
| `CRE_LIBRARIAN_CRE_TEXT_ENRICH` | off | Tied at top; mean slightly lower when on |

## Headline scores (promoted stack)

| Gold / method | Exact | Neighborhood (Related ∪ Contains, 1 hop) |
|---------------|------:|------------------------------------------:|
| AI-topic LLM gold, offline rescore of SUMMARY+margin preds | 33/62 (53.2%) | 52/62 (83.9%) |
| Earlier grid best cell (prior canonical gold) | 27/62 (43.55%) | — |

Neighborhood definition:
[Evaluation and metrics](evaluation-and-metrics.md).

## Reproduce

```bash
export CRE_LIBRARIAN_CRE_SUMMARY=1
export CRE_LIBRARIAN_MARGIN_GAMMA=0.85
export CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector
export CRE_LIBRARIAN_SHORTLIST_JUDGE=0
export NO_LOAD_GRAPH_DB=1

PYTHONPATH=. python scripts/oie_owasp_eval/run_experiment.py \
  --config scripts/oie_owasp_eval/experiments/stack_winners.yaml \
  --keep-all-knowledge
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
- Shortlist judge ON: blocked by provider hangs during factorial runs.
- Live Module C re-run on every gold revision still required when fixtures change;
  offline rescore reuses cached predictions.
