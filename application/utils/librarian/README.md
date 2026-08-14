# Module C — The Librarian

Module C is the decision stage of the OWASP Integrated Ecosystem (OIE) pipeline.
Module A harvests changes from OWASP repositories, Module B filters the noise and
writes what survives to `knowledge_queue`, and **Module C reads that queue and
decides what each chunk means**: link it to a CRE automatically, or route it to a
human.

```text
A (harvester) ──▶ harvest_input ──▶ B (noise filter) ──▶ knowledge_queue ──▶ C (librarian) ──▶ LinkProposal
                                                                                            └▶ ReviewItem ──▶ D (HITL)
```

C never guesses quietly. Every chunk leaves as one of two RFC envelopes, each
carrying the full retrieval audit that produced it, so a decision can always be
explained after the fact.

## The stages

| Stage | Module | What it does |
|---|---|---|
| **C.-1** | `schemas.py`, `config_loader.py` | RFC contracts, config, the read-only mirror of B's `knowledge_queue` row |
| **C.0** | `section_validator.py` | Input boundary — validates and adapts a queue row into an internal `Section` without re-normalizing text |
| **C.0.5** | `explicit_link_resolver.py` | Deterministic path: a chunk that cites a CRE id resolves with no ML at all |
| **C.1** | `candidate_retriever.py` | Embedding retrieval over the CRE hub — produces a shortlist |
| **C.2** | `cross_encoder.py` | Cross-encoder reranker — re-sorts that shortlist |
| **C.3** | `calibration/temperature.py` | Temperature scaling — turns a rerank logit into an honest probability, gated at ECE < 0.10 |
| **C.4** | `decision_engine.py`, `emitter.py` | `decide()` thresholds the confidence; the emitter builds the `LinkProposal` or `ReviewItem` |

Supporting the live path:

| Module | Role |
|---|---|
| `pipeline.py` | Runs C.0 → C.4 over a batch. Persistence-free and hermetic |
| `knowledge_source.py` | Where rows come from — `DbKnowledgeSource` (live) or `FixtureKnowledgeSource` (JSONL) |
| `envelope_sink.py` | Where envelopes go — `DbEnvelopeSink` (writes `decision_queue`, the C→D handoff), `JsonlEnvelopeSink` (file mirror), `NullEnvelopeSink` (dry runs) |
| `queue_consumer.py` | Stamps `consumed_at` back on B's queue. Idempotent; never deletes |
| `queue_runner.py` | The live entry point: drain → decide → persist → retire |
| `factory.py` | Builds the live C.1/C.2/C.3 components from config + the OpenCRE database |
| `safety_guard.py` | The blocking-flag seam `decide()` accepts. Ships as `NullSafetyGuard` |
| `hub_firewall.py` | TRACT hub firewall — strips candidates that leak the answer during evaluation |

## The two rules that matter

**1. A row is only retired if its envelope survived.** Marking a queue row
consumed tells Module B never to offer that chunk again. Doing that while the
envelope goes nowhere destroys the chunk outright. So `queue_runner` refuses to
stamp anything unless it was given a sink that reports `persists=True` *and* that
sink accepted the batch. Dry runs use `NullEnvelopeSink`, which reports `False`,
so a dry run can never consume.

**2. Errors and refusals are different.** A row rejected at the C.0 boundary is
consumed — re-reading a malformed row forever helps nobody, and the same goes for
a row B wrote that C cannot even model. A row that *errored* mid-pipeline (an
embedding timeout, a cross-encoder hiccup) is left unconsumed, because the next
run should retry it. `RunStats` counts them separately on purpose.

`UNCERTAIN` rows are never read and so are never consumed. They are Module D's,
per the B→C contract, and C filters them out in the query rather than at the
boundary — a row C never reads is a row C never retires, which is what keeps D's
queue intact.

## Design constraints

**Hermetic by default.** Nothing in this package imports the database at module
scope. `factory.py` is the single boundary where that stops being true, and even
there the imports are function-local. That is why the whole package is testable
without a DB, an API key, or a model download.

**Seams, not implementations.** C.1 takes an `embed_fn`, C.2 a `score_fn`, C.3 a
scaler, C.4 a safety guard. Each is a `Protocol`, so the live components and the
test stubs are interchangeable and the decision logic stays model-free.

**Declared-degraded over silently-degraded.** `NullSafetyGuard` evaluates nothing
and *says so* — its verdict carries `evaluated=False`, the pipeline counts those
rows, and the runner reports the count. An unevaluated safety path must never
look identical to a clean one.

## Running it

See [the runbook](../../../docs/gsoc_2026_module_c/runbook.md) for setup, live
runs, and troubleshooting. The short version:

```bash
# hermetic regression harness — no DB, no key, no model
python scripts/evaluate_librarian.py \
    --dataset application/tests/librarian/fixtures/golden_dataset.json

# dry run over a JSONL fixture
python cre.py --run_librarian --librarian_dry_run \
    --librarian_source application/tests/librarian/fixtures/sample_knowledge_queue.jsonl

# the full test suite
python -m pytest application/tests/librarian/
```

## Contracts

- **B → C:** [`docs/gsoc_2026_module_b/module_c_contract.md`](../../../docs/gsoc_2026_module_b/module_c_contract.md)
  — the `knowledge_queue` table, column by column.
- **C → D:** the `LinkProposal` / `ReviewItem` envelopes in `schemas.py`, pinned
  to the vendored RFC schemas under `_rfc_schemas/`.

## The C → D handoff

A real run writes one row per decided chunk to **`decision_queue`** — the mirror
of what B does for C through `knowledge_queue`. Module D reads the rows it cares
about and sets `consumed_at`; nothing is ever deleted, so the table doubles as the
audit trail of what C decided and what D did with it.

Both outcomes share the table, separated by `status`:

| `status` | envelope | consumer |
|---|---|---|
| `linked` | `LinkProposal` | the graph writer |
| `review_required` | `ReviewItem`, with a `reason_code` | Module D's HITL review |

The whole RFC envelope is stored in `envelope`, retrieval audit included, so a
decision stays explainable long after the run. The columns beside it are
projections for filtering, not a second source of truth.

Inserts are `ON CONFLICT (chunk_id, pipeline_run_id) DO NOTHING`, so replaying a
run is a no-op rather than a duplicate.

Column-by-column spec: [the C → D contract](../../../docs/gsoc_2026_module_c/module_d_contract.md).

## Not built yet

- **The graph writer.** `decision_queue` carries the `linked` rows, but nothing
  yet reads them and commits an edge into the CRE graph. The rule that writer
  must honour is stated in `safety_guard.py`: it **must refuse to run behind a
  guard reporting `evaluated=False`.** Retiring a queue row without the safety
  path is recoverable; committing a wrong link into a graph other tools read as
  truth is not.
- **The SafetyGuard detector.** The seam is wired; the out-of-distribution
  scoring, conformal prediction, and update detection behind it are future work.
