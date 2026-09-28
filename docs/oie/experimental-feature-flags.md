# Experimental feature flags

These librarian levers and experiment YAMLs were evaluated on the OIE B2 harness
and **not** promoted for the exact Links bar. They remain in-tree as **dead code**
(env default off) so a later merge can keep the implementations without enabling
them. The promoted stack is only:

- `CRE_LIBRARIAN_CRE_SUMMARY=1`
- `CRE_LIBRARIAN_MARGIN_GAMMA=0.85`

See `docs/oie/` on the evaluation branch for the human-facing guide.

## What was tried and did not win (exact Links)

Evidence layers: (A) 512-combo grid on prior canonical gold,
(B) one-factor Step 2/3 matrices, (C) hop soft scores. Prefer citing which layer.

| Flag / stack | Exact evidence | Soft / notes | Verdict |
|--------------|----------------|--------------|---------|
| `CRE_SUMMARY=0` | Grid mean 0.354 vs 0.389 with summary; max 0.377 vs 0.436 | — | Clear loser |
| `DUAL_INDEX=1` | Step2 32/62 vs summary 36/62; with summary, grid mean lower | Can raise neighborhood d1 while hurting exact | Not for Links bar |
| `USE_RRF=1` (needs dual) | Step2 34/62 < summary alone; RRF mean lower with dual | [Cormack et al. RRF](https://dl.acm.org/doi/10.1145/1571941.1572114) | Does not beat summary |
| `HUB_LEAF_CAGE=1` | Step3 28/62 (45.2%); grid hub=1 mean 0.359 vs 0.383 | High-risk allowlist | Hurts |
| `CONTEXT_ENRICH=1` alone | 22/62 (35.5%); grid ~flat | Prefix Standard/Section labels | No help as one-factor |
| `FOCUS_QUERY=1` | Grid mean 0.368 vs 0.375 off | First CE on stripped focus text | Neutral / slight drag |
| `CRE_TEXT_ENRICH=1` | Tied at top 0/1; mean slightly lower when on | Append linked standard prose to C.2 | Neutral |
| Hybrid nameheavy (β=3 / γ=0.15) | Tied max with Lawrence; mean lower | Title-heavy mix | Prefer Lawrence defaults |
| `MARGIN_GAMMA=0.85` vs off | Identical max/mean when SUMMARY=1 on grid | Still promoted for multi-link precision | Neutral on exact alone |
| `SHORTLIST_JUDGE=1` | Not in grid | Gemini hangs | Untested |
| Trained CE | Deferred | — | Untested |

Worst grid cells (~30.6% exact): SUMMARY=0 + hub_leaf=1 + nameheavy + cre_text_enrich.

## Experiment YAMLs kept here

| File | Flag under test |
|------|-----------------|
| `scripts/oie_owasp_eval/experiments/dual_index.yaml` | `CRE_LIBRARIAN_DUAL_INDEX` |
| `scripts/oie_owasp_eval/experiments/rrf.yaml` | `CRE_LIBRARIAN_USE_RRF` (+ dual) |
| `scripts/oie_owasp_eval/experiments/hub_leaf_cage.yaml` | `CRE_LIBRARIAN_HUB_LEAF_CAGE` |
| `scripts/oie_owasp_eval/experiments/context_enrich.yaml` | `CRE_LIBRARIAN_CONTEXT_ENRICH` |

Implementation modules live in `application/utils/librarian/` (flag-gated, default
off). Experiment YAMLs under `scripts/oie_owasp_eval/experiments/` re-run the
non-winning stacks for research only — do not write live Links from them.

## Theory pointers (why these existed)

- Dual index (header→names, body→summaries): multi-representation retrieval; length-based routing failed on several Top10 sections.
- RRF: fuse uncalibrated pools by rank ([SIGIR 2009](https://dl.acm.org/doi/10.1145/1571941.1572114)).
- Hub→leaf cage: restrict to Contains children of top hub hits — precise when hubs are right, brittle when hubs are wrong.
- Context enrich: weakly supervised query rewriting via labels; insufficient alone on this corpus.

## Do not write live Links from these matrices
