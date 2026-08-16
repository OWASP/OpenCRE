# Module C (The Librarian) — runbook

How to run Module C, what each knob does, and what to do when a run goes wrong.

The package overview lives in
[`application/utils/librarian/README.md`](../../application/utils/librarian/README.md).
The table C reads from is specified in
[`module_c_contract.md`](../gsoc_2026_module_b/module_c_contract.md).

---

## 1. The three ways to run C

### a. Hermetic regression harness — no DB, no key, no model

This is what CI runs and what you should run before every push.

```bash
python scripts/evaluate_librarian.py \
    --dataset application/tests/librarian/fixtures/golden_dataset.json
```

Exercises the C.0 boundary and the C.0.5 explicit resolver over all 319 golden
rows. Exits non-zero if the explicit-slice gate fails, or if the boundary rejects
everything (see §5).

The semantic reports stay off here deliberately: there are no CRE vectors
offline, and seeding the candidate pool from golden text is exactly the leakage
the hub firewall exists to strip.

### b. Live evaluation — measures C.1 through C.4

Needs a populated embedding cache and an embedding-capable LLM.

```bash
python scripts/evaluate_librarian.py \
    --dataset application/tests/librarian/fixtures/golden_dataset.json \
    --use_live_embeddings --cache_file standards_cache.sqlite
```

Adds four reports on top of the hermetic ones: C.1 recall@k, C.2 rerank top-1,
the C.3 ECE gate, and C.4 decision accuracy. All four share one retrieve+rerank
pass and one fitted `T` — the pipeline is built once per run, not once per
report.

**C.3 is the only *additional* gate a live run adds.** A failed or skipped ECE
gate returns non-zero, so a live run cannot pass without calibration having
actually run, and C.4 stays informational. The hermetic gates still apply on top:
a failed C.0.5 explicit slice, or a C.0 boundary that rejects the whole dataset,
fails the run in either mode (§5).

### c. Live queue drain — the real pipeline

```bash
# dry run first: reads, decides, persists nothing, retires nothing
python cre.py --run_librarian --librarian_dry_run --run_id <pipeline_run_id>

# for real: decisions land in decision_queue, and only then are rows retired
python cre.py --run_librarian --run_id <pipeline_run_id>

# optionally mirror the same batch to a file for eyeballing
python cre.py --run_librarian --run_id <pipeline_run_id> \
    --librarian_envelopes_out envelopes.jsonl
```

A real run writes to **`decision_queue`**, the table Module D reads — that is the
contract. `--librarian_envelopes_out` only adds a JSONL copy alongside it; it is
a debugging convenience, not the handoff. See
[the C → D contract](module_d_contract.md).

Or against a JSONL fixture instead of the live queue:

```bash
python cre.py --run_librarian --librarian_dry_run \
    --librarian_source application/tests/librarian/fixtures/sample_knowledge_queue.jsonl
```

---

## 2. CLI flags

| Flag | Meaning |
|---|---|
| `--run_librarian` | Run Module C. With `--run_id`, drains B's live `knowledge_queue`; without it, walks a JSONL fixture |
| `--run_id` | The `pipeline_run_id` to drain. Scopes the run to one orchestrator pass |
| `--librarian_dry_run` | Read and decide, but persist nothing and stamp nothing |
| `--librarian_source` | Path to a `knowledge_queue` JSONL. **Not valid with `--run_id`** — the CLI rejects the combination rather than silently ignoring one |
| `--librarian_envelopes_out` | Optional JSONL mirror of the batch. A real run always writes `decision_queue`; this only adds a file copy |

A real run always has a persisting sink — `decision_queue` — so it can safely
retire rows. The runner still refuses to consume behind a sink that reports
`persists=False`, which is what makes a dry run harmless.

---

## 3. Configuration

All tunables are `CRE_LIBRARIAN_*` environment variables.

| Variable | Default | What it is |
|---|---|---|
| `CRE_LIBRARIAN_CROSSENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | C.2 reranker model |
| `CRE_LIBRARIAN_RETRIEVER_BACKEND` | `in_memory` | `in_memory` or `pgvector` |
| `CRE_LIBRARIAN_TOP_K_RETRIEVAL` | `20` | C.1 shortlist size |
| `CRE_LIBRARIAN_TOP_K_RERANK` | `5` | How many C.2 re-sorts |
| `CRE_LIBRARIAN_LINK_THRESHOLD` | `0.8` | **τ** — the auto-link bar |
| `CRE_LIBRARIAN_TEMPERATURE` | `1.0` | **T** — C.3's fitted temperature |
| `CRE_LIBRARIAN_BATCH_SIZE` | `32` | Rows per batch |
| `CRE_LIBRARIAN_ECE_TARGET` | `0.10` | Calibration gate |

**Two of these are measured, not chosen.**

`CRE_LIBRARIAN_TEMPERATURE` is fitted by the live harness, which prints it. There
is nowhere else it is stored. The default of `1.0` is the identity transform — an
*uncalibrated* softmax that is honest about being unfitted rather than pretending
to a temperature nobody measured. **After any change to the retriever, the
reranker, or the CRE corpus, re-fit it and update the variable.**

`CRE_LIBRARIAN_LINK_THRESHOLD` is τ, held at 0.80 by the Week 7 sweep. Lowering it
trades review precision for auto-link recall. The sweep found no better value —
do not lower it without re-running that analysis.

---

## 4. Setup

### The embedding cache

C.1 retrieves over CRE-node vectors. After the pgvector migration (`c7d8e9f0a1b2`),
vectors live only in `embedding_vec`. A legacy `standards_cache.sqlite` with the
old CSV `embeddings` column will be refused by the ORM:

```bash
python scripts/rewrite_sqlite_embeddings_to_vec.py --db standards_cache.sqlite
```

Rerun-safe: it reports `already embedding_vec-only; nothing to do` if applied.

### The cross-encoder

Downloaded from the HF Hub on first use. Set `HF_TOKEN` to avoid rate limits.

---

## 5. Troubleshooting

**`embeddings.embedding_vec is required; the legacy CSV embeddings column is no longer a supported store`**
Your cache predates the pgvector migration. Run the rewrite script in §4.

**`validation (C.0): 0/319 rows validated ... FAILED (gates did not run)`**
Every golden row was rejected at the boundary. Almost always means the synthetic
row shape in `queue_row_from_golden` has drifted from Module B's live
`knowledge_queue`. This exact failure happened when B's table moved in #989 — the
adapter kept minting the old flat row. The guard exists because the *old*
behaviour was worse: with nothing validated, the explicit gate had nothing to
count, skipped itself, and the run still exited 0.

**`--librarian_source reads a fixture and cannot be combined with --run_id`**
Pick one. A fixture path with a run id would silently ignore one of them.

**A real run reports rows decided but nothing consumed**
The sink refused the batch. Consumption is gated on persistence — this is the
safe failure, not a bug. Check the `decision_queue` insert did not raise.

**`decision_queue` shows fewer rows than the run decided**
Inserts are `ON CONFLICT (chunk_id, pipeline_run_id) DO NOTHING`, so a replayed
run writes nothing new. That is idempotence working, not loss — the rows from the
first run are still there.

**An `UNCERTAIN` row went to review despite a high confidence**
Working as intended. C reads both of B's labels, so an `UNCERTAIN` chunk runs the
full pipeline and the reviewer gets candidates and the audit — but it always
routes to review with `reason_code = SOURCE_UNCERTAIN`, whatever it scored. B's
uncertainty is about *whether the chunk is security knowledge*; C's confidence is
about *which CRE it matches*. A confident answer to the second does not settle
the first, so the chunk goes to a human either way.

**Rows keep reappearing across runs**
They errored mid-pipeline rather than being decided. Errored rows are left
unconsumed on purpose so the next run retries them. Check the logs for the chunk
and artifact id; `RunStats.errored` counts them separately from `skipped`.

**ECE gate fails or is skipped**
A degenerate calibration set — all top-1 labels the same class — cannot identify
`T`. The harness fails rather than skipping, so this is reported, not hidden.
Widen the slice selection so both the positive and hard_negative slices are in.

---

## 6. Known limitations

**Postgres is not verified.** Everything here has been exercised against SQLite
through the same SQLAlchemy models. The column types and the migration are
written for both, and `consumed_at` is normalised to naive UTC precisely because
the two dialects differ, but no run has been made against a real Postgres. Treat
the first one as a test.

## 7. Tests

```bash
# everything (hermetic — no DB, key, or model needed)
python -m pytest application/tests/librarian/

# the live-drain path specifically
python -m pytest application/tests/librarian/queue_runner_test.py \
                 application/tests/librarian/queue_consumer_test.py
```

The queue tests use a real SQLAlchemy session with real row inserts and real
`consumed_at` assertions. Only the ML seams are stubbed.
