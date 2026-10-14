# Soft production metric: CRE neighborhood (Related ∪ Contains)

**Exact Links bar** stays canonical gold ID intersection (ship / write Links).

**Neighborhood soft bar** (gap-analysis / RAG usefulness): a section hits if any
predicted CRE is exact **or** 1-hop Related **or** 1-hop Contains (PartOf is the
reverse Contains edge in `cre_links` — not stored separately).

On SUMMARY+margin preds vs AI-topic LLM gold (2026-09-22):

| Metric | Score |
|--------|------:|
| Exact | 33/62 (53.2%) |
| Neighborhood (d1) | 52/62 (83.9%) |

Scorer: `scripts/oie_owasp_eval/score_b2_hop_distance.py` + `hop_distance.py`.
Do **not** put Related-expand back into canonical gold.
