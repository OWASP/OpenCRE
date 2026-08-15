# Module B — How to Run It (Orchestrator Runbook)

**Audience:** whoever builds/operates the daily orchestrator. **Status:** v0.2 (2026-08-16).
Companion to `module_c_contract.md` (the B→C contract). This is the operational *how*.

Module B is a **stateless batch step**: the orchestrator invokes it once per harvest run; it reads that run's chunks from a DB table, classifies them, writes the keepers to another table, and exits with a JSON summary. It does not run continuously and does not schedule itself.

---

## 1. One-time setup

**Tables.** Module B owns two tables, created by its Alembic migration
`d4e5f6a7b8c9_add_module_b_tables` (part of the chain — other modules' migrations
now chain after it, so it is no longer the head):
- `harvest_input` — Module A writes here; B reads.
- `knowledge_queue` — B writes here; Module C reads.

Apply with:
```bash
FLASK_APP=cre.py FLASK_CONFIG=development flask db upgrade
```
A full from-empty `flask db upgrade` on Postgres runs the whole chain, creating
Module B's tables at migration `d4e5f6a7b8c9` (now mid-chain; the current head
moves as other modules add migrations after it — the from-empty upgrade still
reaches B's tables regardless). The earlier `uq_pair` duplicate-index bug is
fixed and merged. One caveat: **C's pgvector migration (`c7d8e9f0a1b2`)
requires `CRE_EMBED_EXPECTED_DIM` to be set** on an empty DB (it can't infer the
vector dimension with no embeddings yet) — a pre-existing requirement of that
migration, e.g. `CRE_EMBED_EXPECTED_DIM=3072 flask db upgrade`. Postgres needs
the `vector` extension (use the `pgvector/pgvector` image or `CREATE EXTENSION
vector;`).

**Environment variables:**
| Var | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | LLM credential (Gemini) | — (required) |
| `CRE_NOISE_FILTER_LLM_MODEL` | classification model | `gemini/gemini-2.5-flash-lite` |
| `CRE_NOISE_FILTER_BATCH_SIZE` | chunks per LLM request | `10` |
| `CRE_NOISE_FILTER_MAX_CHARS` | per-chunk truncation | `1500` |
| `CRE_NOISE_FILTER_CONFIDENCE_THRESHOLD` | KNOWLEDGE-below → UNCERTAIN | `0.8` |

Module B needs no ML libraries (no torch/sentence-transformers) — just `litellm` (in the slim prod requirements) + the Gemini key.

---

## 2. The input table `harvest_input` (Module A writes)

One row per harvested chunk:
| Column | Notes |
|---|---|
| `id` | any stable PK |
| `pipeline_run_id` | groups a run — B reads exactly this |
| `status` | `pending` (A sets) → `processed`/`error` (B sets) |
| `payload` | **JSONB** — Module A's ChangeRecord v0.3 (nested `source`/`span`/`locator`), written as-is |
| `created_at` | timestamp |

B reads `WHERE pipeline_run_id = :run_id AND status = 'pending'`.

---

## 3. Invoking Module B (the command the orchestrator runs)

```bash
python cre.py --run_noise_filter --run_id <pipeline_run_id> --cache_file <db-url>
```
- `--run_id` — the run to process (**required**).
- `--cache_file` — the database URL (e.g. `postgresql://user:pass@host:5432/opencre`).
- `--noise_filter_dry_run` — optional; classify but write nothing / mark nothing (for testing).

The process runs the gate (regex path filter → sanitize → LLM classify), writes keepers, marks the input rows, and exits.

---

## 4. Completion signal (how the orchestrator knows it's done)

- **Exit code `0`** = success; **non-zero** = hard failure (e.g. DB unreachable) → safe to retry the same `run_id` (B is idempotent).
- **stdout** = a one-line JSON summary:
```json
{"run_id":"20260201T020000Z","read":512,"parse_errors":0,"dropped_noise":172,
 "kept_knowledge":300,"kept_uncertain":40,"inserted":338,"deduped":2,
 "dry_run":false,"status":"ok"}
```
| Field | Meaning |
|---|---|
| `read` | input rows for the run |
| `parse_errors` | payloads that failed validation (rows marked `error`) |
| `dropped_noise` | dropped as NOISE (regex + LLM) — not queued |
| `kept_knowledge` / `kept_uncertain` | classified as KNOWLEDGE / UNCERTAIN |
| `inserted` | rows written to `knowledge_queue` |
| `deduped` | keepers skipped as duplicate content |
| `status` | `ok` (per-chunk errors are contained, not fatal) |

---

## 5. The output table `knowledge_queue` (Module C reads)

B inserts `KNOWLEDGE` and `UNCERTAIN` rows (never `NOISE`), deduped on `content_hash`. Module C reads unconsumed rows and sets `consumed_at`. Full schema + read query: `module_c_contract.md` (v0.2).

---

## 6. Orchestrator sequencing

```
A (writes harvest_input for run R)  ──finishes──►
B: python cre.py --run_noise_filter --run_id R --cache_file <db>
   └─ exit 0 + JSON summary  ──►
C (reads knowledge_queue)
```
The orchestrator **serialises** the steps: call B only after A has finished writing run R; call C only after B exits 0. B never polls or waits — sequencing is the orchestrator's job.

## 7. Guarantees

- **Recall-first:** only NOISE is dropped; KNOWLEDGE and UNCERTAIN always reach the queue (no security knowledge lost).
- **Idempotent:** input rows are marked `processed`; re-invoking the same `run_id` is safe. `UNIQUE(content_hash)` collapses duplicate content.
- **Error isolation:** an unparseable input row → marked `error` (not fatal); a failed LLM batch → those chunks become `UNCERTAIN` (never dropped); infrastructure failure → non-zero exit for the orchestrator to retry.

---

## Open enhancement (optional)

Today the DB is passed via `--cache_file`. If you'd prefer 12-factor/env-based config, we can make `--run_noise_filter` fall back to `DATABASE_URL`/`DEV_DATABASE_URL` when `--cache_file` is omitted — say the word.
