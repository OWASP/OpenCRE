# Module B — final metrics

The numbers in **Results** below come from a single run of the harness over the
committed labeled set. It runs the **real** gate (Stage 1 regex → Stage 1.5
sanitize → Stage 2 LLM) and scores its predictions against the gold labels. (The
*Baseline → final* section further down is a historical comparison across two
different runs — see the note there.)

```bash
python scripts/evaluate_noise_filter.py
```

**Environment:** model `gemini/gemini-2.5-flash-lite`, batch size 10, confidence
threshold 0.8, regex stage on. Run 2026-08-22 (branch `module_b_w6`).

## The labeled set

`application/tests/noise_filter/fixtures/labeled_data.json` — 100 chunks harvested
from four OWASP repos (WSTG, ASVS, CheatSheetSeries, SAMM) in Module A's record
shape, hand-labelled under the **recall-first** rule: KNOWLEDGE = any security
signal; NOISE = purely organizational content (sponsorship, meetings, CI, layouts);
UNCERTAIN reserved for genuine 50/50s.

| Label | Count |
|---|---|
| KNOWLEDGE | 56 |
| NOISE | 44 |
| UNCERTAIN | 0 |

## Results

```text
accuracy:  93/100 = 0.930
```

### Recall-first headline

The metric that matters: a security chunk wrongly dropped (`KNOWLEDGE → NOISE`) is
lost forever *before* Module C ever sees it. That must be zero.

| | |
|---|---|
| **KNOWLEDGE recall** | **1.000** |
| **KNOWLEDGE → NOISE leakage** | **0 / 56** |

Zero security knowledge dropped.

### Confusion matrix (rows = gold, cols = predicted)

| gold ↓ / pred → | KNOWLEDGE | NOISE | UNCERTAIN |
|---|---|---|---|
| **KNOWLEDGE** | 56 | 0 | 0 |
| **NOISE** | 7 | 37 | 0 |
| **UNCERTAIN** | 0 | 0 | 0 |

All 7 errors are in the **safe** direction (NOISE → KNOWLEDGE): they cost a little
downstream compute in Module C's cross-encoder, never lost knowledge.

### Per-class precision / recall / F1

| Class | P | R | F1 |
|---|---|---|---|
| KNOWLEDGE | 0.889 | 1.000 | 0.941 |
| NOISE | 1.000 | 0.841 | 0.914 |
| UNCERTAIN | 0.000 | 0.000 | 0.000 |

(The gold has no UNCERTAIN samples, so the harness reports `0.000` across that row.)
These are **pipeline** metrics — the harness scores the combined regex + LLM
predictions. NOISE precision is **1.000**: nothing the pipeline marked NOISE was
actually security content, so the recall-first bias cost no false drops.

### Stage 2 (LLM) only

| | |
|---|---|
| reached the LLM | 98 (regex dropped 2) |
| LLM accuracy | 91 / 98 = 0.929 |
| mean confidence | 0.944 |

## Baseline → final (historical)

This table is a **historical** comparison across two *different* runs — it does
**not** come from the single command above. The baseline is an earlier Week-4 run
on a slightly different gold set (55 KNOWLEDGE), so `0.820 → 0.930` is a directional
story, not a like-for-like accuracy delta. The point it makes: the gain came from
fixing the **gold** and sharpening the **prompt**, never from trading away recall.

| (historical) | accuracy | KNOWLEDGE recall | leakage |
|---|---|---|---|
| baseline (untuned prompt, Week-4 gold) | 0.820 | 1.000 | 0 / 55 |
| **final (current gold)** | **0.930** | **1.000** | **0 / 56** |

*(The gold was corrected between the two runs — 9 principled relabels resolving
stale UNCERTAIN and heading-only cases — which is why the leakage denominator moved
55 → 56. Recall and leakage stayed perfect across the change.)*

## Reproduce

Both inputs are committed, so the **evaluation procedure** reproduces from a clean
checkout. Because Stage 2 calls a live Gemini model, the exact per-record
predictions — and the last decimal of each metric — can vary run to run; the
recall-first behaviour (100% KNOWLEDGE recall, 0 leakage) is what stays stable.

- harness — `scripts/evaluate_noise_filter.py`
- labeled set — `application/tests/noise_filter/fixtures/labeled_data.json`

```bash
export GEMINI_API_KEY=...        # a cheap-model key; the run is ~10 batched calls
python scripts/evaluate_noise_filter.py
```

Flags: `--limit N`, `--threshold T`, `--model M`, `--no-regex`, `--out PATH`.
