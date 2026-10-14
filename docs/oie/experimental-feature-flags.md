# Experimental feature flags

These librarian levers were evaluated on the OIE B2 / full-pipeline harness and
are **not** part of the shipped d1-winner defaults (or are default-off knobs for
follow-up). Implementations may remain in-tree behind env gates.

> **Merge note:** Unused experiment YAMLs / dead levers may be **removed on merge**
> if they have no production callers and no planned follow-up.

## Promoted (see feature-flags.md)

Current ship path is documented in [feature-flags.md](feature-flags.md):

- `CRE_LIBRARIAN_CRE_SUMMARY=1`
- `CRE_LIBRARIAN_MARGIN_GAMMA=0.85` (wired in Module C)
- `CRE_LIBRARIAN_DUAL_INDEX=1` (code default on)
- `CRE_LIBRARIAN_SHORTLIST_JUDGE=1` + `MAX_PICKS=3` (full-pipeline)
- `CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP=8`
- `CRE_LIBRARIAN_LEAF_DRILLDOWN=1` (E1/E2/FORCE off)

## What was tried and did not win (or is opt-in only)

Evidence layers: (A) 512-combo grid on prior canonical gold,
(B) one-factor Step 2/3 matrices, (C) hop soft scores / cold-start.

| Flag / stack | Exact evidence | Soft / notes | Verdict |
|--------------|----------------|--------------|---------|
| `CRE_SUMMARY=0` | Grid mean 0.354 vs 0.389 with summary | — | Clear loser |
| `DUAL_INDEX=0` | Older Links-bar matrices preferred off | Product/d1 path ships dual **on** | Historical exact note only |
| `USE_RRF=1` (needs dual) | Step2 34/62 < summary alone | [Cormack et al. RRF](https://dl.acm.org/doi/10.1145/1571941.1572114) | Off |
| `HUB_LEAF_CAGE=1` | Step3 28/62 (45.2%) | High-risk allowlist | Off |
| `CONTEXT_ENRICH=1` alone | 22/62 (35.5%) | Prefix labels | Off |
| `FOCUS_QUERY=1` | Grid mean 0.368 vs 0.375 off | First CE on stripped focus | Off |
| `CRE_TEXT_ENRICH=1` | Tied at top; mean slightly lower | Append linked standard prose | Off |
| Hybrid nameheavy (β=3 / γ=0.15) | Tied max; mean lower | Prefer Lawrence defaults | Off |
| `LEAF_DRILLDOWN_FORCE_RESOURCES=api` | GitHub d1↑; API exact 60→50 | Cold-start post-60 | **Do not ship** |
| `LEAF_DRILLDOWN_KEEP_HUB` / `HUB_FIRST` | E1/E2 | Not in d1 winner | Off |
| Trained CE | Deferred | — | Untested |

Worst grid cells (~30.6% exact): SUMMARY=0 + hub_leaf=1 + nameheavy + cre_text_enrich.

## Experiment YAMLs kept here

| File | Flag under test |
|------|-----------------|
| `scripts/oie_owasp_eval/experiments/dual_index.yaml` | Historical dual-off matrix |
| `scripts/oie_owasp_eval/experiments/rrf.yaml` | `CRE_LIBRARIAN_USE_RRF` (+ dual) |
| `scripts/oie_owasp_eval/experiments/hub_leaf_cage.yaml` | `CRE_LIBRARIAN_HUB_LEAF_CAGE` |
| `scripts/oie_owasp_eval/experiments/context_enrich.yaml` | `CRE_LIBRARIAN_CONTEXT_ENRICH` |

Implementation modules live in `application/utils/librarian/` (flag-gated).
Experiment YAMLs under `scripts/oie_owasp_eval/experiments/` re-run research
stacks only — do not write live Links from them.

## Gold / overlay note

Canonical LLM Top 10 mapping gold lives at
`application/tests/fixtures/owasp_mappings/owasp_llm_top10_2025.json` (hub AI
CREs, #1124). The copy under `scripts/oie_owasp_eval/fixtures/b2_gold/` is a
**non-scoring overlay** for rebuild helpers — do not treat it as the answer key.

## Theory pointers (why these existed)

- Dual index (header→names, body→summaries): multi-representation retrieval.
- RRF: fuse uncalibrated pools by rank ([SIGIR 2009](https://dl.acm.org/doi/10.1145/1571941.1572114)).
- Hub→leaf cage: restrict to Contains children of top hub hits — brittle when hubs are wrong.
- Context enrich: weakly supervised query rewriting via labels; insufficient alone.

## Do not write live Links from these matrices
