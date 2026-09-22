# Evaluation and metrics

OIE mapping quality is measured on fixed **gold** fixtures: each standard section
lists acceptable CRE identifiers. Two bars are reported. They answer different
questions and must not be mixed when claiming a ship number.

## Exact Links bar

A section is a **hit** if the intersection of predicted CRE ids and gold CRE ids
is non-empty.

- Use this bar for: deciding whether to write Links, PR gate headlines, regression
  against canonical fixtures under `application/tests/fixtures/owasp_mappings/`.
- Do **not** expand gold with Related or Contains neighbors. Expanding gold
  trains the system to accept near-misses as if they were correct Links.

On the promoted stack (`CRE_SUMMARY=1`, `MARGIN_GAMMA=0.85`) against AI-topic
LLM Top10 gold (2026-09-22 offline rescore of cached predictions):

**33 / 62 (53.2%)** exact.

## CRE neighborhood soft bar

A section is a **soft hit** if any predicted CRE is an exact gold id **or** lies
one hop from a gold id on **Related ∪ Contains** in `cre_links`. PartOf is the
reverse Contains edge and is not stored separately.

- Use this bar for: gap-analysis / RAG usefulness (“did we land in the right part
  of the CRE graph?”).
- Scorer: `scripts/oie_owasp_eval/score_b2_hop_distance.py` (see also
  `hop_distance.py` and `experiments/NEIGHBORHOOD_METRIC.md`).

Same predictions as above:

**52 / 62 (83.9%)** neighborhood (distance ≤ 1).

## Gold sets used in B2

| Fixture | Role |
|---------|------|
| Classical mapping fixtures (Top10, API, K8s, …) | Gate-style exact scoring |
| LLM Top10 / AI-topic CREs | Canonical LLM gold shared with AI Exchange hub CREs |
| `owasp_asvs_5_0_provisional` | Provisional ASVS 5.0 answer key (v4→v5 remap); 190 sections |

ASVS 5 was historically excluded from default B2 denominators when chapter-sized
bodies caused Module C out-of-memory failures. Section-scoped sources under
`scripts/oie_owasp_eval/fixtures/b2_sources/owasp_asvs_5_0_provisional/` are the
intended input for ASVS-only runs (`run_b2_pr_mappings.py` with other fixtures
excluded, or `run_experiment.py --include-asvs5`).

## How to reproduce a soft score

```bash
# After a B2 report with non-empty predicted ids exists:
PYTHONPATH=. python scripts/oie_owasp_eval/score_b2_hop_distance.py \
  --reports-glob 'asvs5_stack_winners.b2_report.json' \
  --force
```

Reports land under `tmp/oie_owasp_eval/experiments/hop_analysis/`.

## Exhaustive switch grid (context)

A 512-combo factorial over librarian flags (CPU cross-encoder, shortlist judge
off) established that **CRE summaries on** dominate exact accuracy. Full tables
live in `scripts/oie_owasp_eval/experiments/WINNERS.md` and (locally)
`tmp/oie_owasp_eval/experiments/grid/`. Promoted flags are summarized in
[Feature flags](feature-flags.md). Approaches that did not help the exact bar
are documented in [experimental-feature-flags.md](experimental-feature-flags.md)
(dead code; default off).
