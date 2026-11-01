# ASVS full-pipeline + requirement_extract=auto (2026-09-23)

## Setup
- Worktree / branch: `OpenCRE-wt-oie-1088-harness` / `wip/oie-pipeline-eval-harness` @ `d6d4e5cb`
- Baseline tag lineage: `oie-eval-asvs-neighborhood-v1` @ `01f83175`
- Run id: `fullpipe-asvs-extract-20260923T181734Z`
- Stack: SUMMARY+MARGIN (`CRE_LIBRARIAN_CRE_SUMMARY=1`, `CRE_LIBRARIAN_MARGIN_GAMMA=0.85`)
- Extract: `requirement_extract=auto` (wired in `run_full_pipeline.py` ChunkingConfig)
- Queues: cleared all local `harvest_input` / `knowledge_queue` / `decision_queue` before replay (4712 leftovers)
- Gold: canonical provisional ASVS 5.0; soft metric = Related ∪ Contains 1-hop only (`score_b2_hop_distance.py`)

## Harvest effect
- This run: **461** ASVS harvest chunks (extract fired per-chapter, e.g. V6 Auth → 47 segments)
- Prior fullpipe-all ASVS arm: **275** chunks logged — consistent with silent `content_hash` skip when queues were dirty

## Scores (ASVS only, n=190)

| Metric | Prior fullpipe ASVS slice | This re-run | Δ |
|--------|--------------------------:|------------:|--:|
| Exact | 3/190 (1.6%) | 11/190 (5.8%) | +4.2 pp |
| Neighborhood d1 | 70/190 (36.8%) | 82/190 (43.2%) | +6.3 pp |

Buckets this run: `{'one_hop_contains': 64, 'exact': 11, 'multi_hop': 108, 'one_hop_related': 7}`

## Reference (different path — B2 fixture arm, not tarball)
- `asvs5_stack_winners` SUMMARY+MARGIN: exact **45/190 (23.7%)**, d1 **71.6%**
- Gap to fixture exact: **-17.89 pp**

## Takeaway
- Clearing KQ + extract=auto raised exact **3→11** and d1 **70→82** on the full-pipeline GitHub path.
- Absolute accuracy remains far below the B2 fixture arm; Module C still mostly `review_required` (460/461) with only 1 hard `linked`.
- Next accuracy work should chase why tarball+extract underperforms the fixture arm (alignment of section_id / pred CRE selection), not gold fattening.

Artifacts: `tmp/oie_owasp_eval/experiments/full_pipeline_github.b2_report.json`, hop under `hop_analysis/full_pipeline_github.hop.json`, prior snapshot in `experiments/baselines/`.

## Scorer parity + extractor hygiene (same day, code)

### Offline scorecard (same envelopes, no LLM)
| Gate | Exact |
|------|------:|
| Legacy fullpipe suggested_links top2 + chapter union | 11/190 (5.8%) |
| B2 rerank∪vector top2 + per-chunk (parity target) | 20/190 (10.5%) |

### After code: rescored same envelopes
- Exact **20/190 (10.5%)**, d1 **83/190 (43.7%)**
- Confirms scorer under-count was ~half the gap vs B2 fixture (45/190)

### Extractor / builder fixes (needs fresh Module C re-run)
- Table segments = prose only (no pipes, no next-heading bleed)
- Record builder keeps a single `Section-ID: Vn.n.n` when extract prefix present
- Fullpipe `_top2_cre_ids` matches B2; attribution is per-chunk

Next: clear KQ and re-run `--repos asvs` to measure extract impact on ranks.

## Clean extract re-run (`fullpipe-asvs-extract-clean-20260923T190122Z`)

Harvest: 421/461 chunks with a single non-comma Section-ID; V1.1.2 body is prose-only (no table pipes).

| Metric | Dirty+legacy score | Dirty+parity score | **Clean extract+parity** | B2 fixture |
|--------|-------------------:|-------------------:|-------------------------:|-----------:|
| Exact | 5.8% | 10.5% | **65.3%** (124/190) | 23.7% |
| d1 | 43.2% | 43.7% | **76.3%** (145/190) | 71.6% |

Gold in rerank top-2: **0/196** mentions (was ~0 on dirty run). Rank dist when found: `{3: 33, 4: 24, 5: 19, 6: 17, 7: 11}`.
