# Module B → Module C Output Contract

**Audience:** the GSoC 2026 contributor implementing Module C (The Librarian — vector + cross-encoder mapping of filtered knowledge chunks to existing CRE nodes). **Status:** draft **v0.3** (2026-08-16). It documents **Module B's `knowledge_queue` table** and Module C's live consumer — **both now on `main`**. Module C's consumer merged in **PR #1011**: `application/utils/librarian/knowledge_source.py:DbKnowledgeSource` reads unconsumed rows with `llm_label IN ('KNOWLEDGE', 'UNCERTAIN')` (`READABLE_LABELS`), and `librarian/schemas.py:KnowledgeQueueItem` mirrors this table column-for-column.

This document specifies how Module C reads Module B's output. Module B produces; Module C consumes; Module D's HITL UI may also read for review.

---

## Changelog (v0.2 → v0.3)

- **Producer and consumer both shipped.** Module B's `knowledge_queue` table (documented below, 23 columns) is on `main`, and Module C's live consumer is now **merged (#1011)**: `application/utils/librarian/knowledge_source.py:DbKnowledgeSource` reads unconsumed rows filtered by `llm_label IN ('KNOWLEDGE', 'UNCERTAIN')` (`READABLE_LABELS`), ordered by `created_at, id`; and `librarian/schemas.py:KnowledgeQueueItem` mirrors B's `db.KnowledgeQueueItem` column-for-column (`from_attributes=True`, tolerating extra columns).
- **Module C consumes both `KNOWLEDGE` and `UNCERTAIN` (shipped in #1011).** `DbKnowledgeSource` filters `llm_label.in_(READABLE_LABELS)`, where `READABLE_LABELS = ('KNOWLEDGE', 'UNCERTAIN')`. B's `llm_label` is a confidence signal, not a routing directive: C consumes every non-NOISE row and decides internally which chunks need Module D's HITL review — keeping recall-first intact end to end (no security chunk stranded for a label with no downstream consumer).
- **`source_committed_at` type corrected to `String`.** Module B stores it as an ISO-8601 **string** (the value Module A emits, unparsed), not a `DateTime`. Module C parses it to a datetime on read (Pydantic coercion) — no conflict, but the storage type in this contract now matches Module B's actual model/migration.

## Changelog (v0.1 → v0.2)

- **Orchestrated pipeline:** B is now invoked by the daily **orchestrator** (not a manual CLI run). B reads Module A's chunks from a Postgres table, classifies, writes keepers to `knowledge_queue`, and signals the orchestrator "done"; the orchestrator then calls C.
- **Schema aligned to Module A's nested record** (`source` / `span` / `locator`), instead of the old flat `source_repo` / `source_path` / `source_commit_sha`. (Module A contract was v0.3 when this alignment landed; the record shape is unchanged through the current v0.4.)
- **Dedup key changed:** `UNIQUE(content_hash)` (B-computed on the normalized text) replaces `UNIQUE(source_commit_sha, source_path)`. The same normalized content reaching B via two sources or two runs collapses to one row.
- **Source-type-aware:** schema and read query now support the `source.type` discriminator (`github` today; `rss` reserved).

---

## Transport

- **Format:** SQL table `knowledge_queue` in the shared OpenCRE Postgres database (the same DB the orchestrator uses to hand off between modules).
- **Backend:** SQLite for dev/CI/harness; **PostgreSQL** in production (Module C uses pgvector).
- **Producer:** Module B, when the orchestrator invokes it for a run. B inserts `KNOWLEDGE` and `UNCERTAIN` rows; `NOISE` is dropped (recorded only in B's run summary/audit).
- **SQLAlchemy model:** `KnowledgeQueueItem` in `application/database/db.py` (added by Module B at integration, with an Alembic migration that must pass `make alembic-guardrail`).

Why a table (not a Redis queue, JSONL handoff, or upstream's `StagedChangeSet`): durability + history + `consumed_at` semantics + dedup, and it fits the orchestrator's DB-handoff model. Upstream's `ImportRun`/`StandardSnapshot`/`StagedChangeSet` solve *standards versioning*, not filtered-chunk consumption.

## Table schema

This is **Module B's SQLAlchemy model** in `application/database/db.py` — here `BaseModel` is the project's SQLAlchemy declarative base (`BaseModel = sqla.Model`, aliased in `db.py`), **not** Pydantic. Module C's Pydantic *read-side* mirror is a separate class, `application/utils/librarian/schemas.py:KnowledgeQueueItem`, which validates rows read from this table.

```python
class KnowledgeQueueItem(BaseModel):  # SQLAlchemy model (db.py); BaseModel = sqla.Model
    __tablename__ = "knowledge_queue"
    id             = sqla.Column(sqla.String, primary_key=True, default=generate_uuid)
    content_hash   = sqla.Column(sqla.String, nullable=False)       # B-computed dedup key (SHA-256 hex, 64 chars)
    # provenance / traceability (from Module A's record)
    chunk_id        = sqla.Column(sqla.String, nullable=False)
    artifact_id     = sqla.Column(sqla.String, nullable=False)
    pipeline_run_id = sqla.Column(sqla.String, nullable=False)
    schema_version  = sqla.Column(sqla.String, nullable=False)
    source_type     = sqla.Column(sqla.String, nullable=False)       # "github" | "rss"
    source_repo         = sqla.Column(sqla.String, nullable=True)     # github-only
    source_commit_sha   = sqla.Column(sqla.String, nullable=True)
    source_committed_at = sqla.Column(sqla.String, nullable=True)     # ISO-8601 string (C parses)
    feed_url        = sqla.Column(sqla.String, nullable=True)         # rss-only
    post_guid       = sqla.Column(sqla.String, nullable=True)
    locator_kind    = sqla.Column(sqla.String, nullable=False)
    locator_path    = sqla.Column(sqla.String, nullable=False)
    span_index      = sqla.Column(sqla.Integer, nullable=False)
    span_total      = sqla.Column(sqla.Integer, nullable=False)
    span_heading_path = sqla.Column(sqla.Text, nullable=True)         # JSON-encoded list[str]
    # payload + B's verdict
    text          = sqla.Column(sqla.Text, nullable=False)
    llm_label     = sqla.Column(sqla.String, nullable=False)          # KNOWLEDGE | UNCERTAIN
    confidence    = sqla.Column(sqla.Float, nullable=False)
    llm_reasoning = sqla.Column(sqla.Text, nullable=True)
    created_at    = sqla.Column(sqla.DateTime, nullable=False, server_default=sqla.func.now())
    consumed_at   = sqla.Column(sqla.DateTime, nullable=True)
    __table_args__ = (
        sqla.Index("ix_knowledge_queue_unconsumed", "consumed_at"),
        sqla.UniqueConstraint("content_hash", name="uq_content_hash"),
    )
```

| Column | Purpose for Module C |
|---|---|
| `id` | Stable UUID. Use as the source identity for CRE-mapping logs. |
| `content_hash` | B's SHA-256 of the normalized **original** chunk text; the dedup key (stable across sanitizer changes). |
| `chunk_id`, `artifact_id`, `pipeline_run_id`, `schema_version` | Traceability back to Module A's record (and to Module D's review UI). |
| `source_type` + `source_*` / `feed_*` | Provenance discriminator. `github` populates `source_repo`/`source_commit_sha`/`source_committed_at`; `rss` populates `feed_url`/`post_guid`. |
| `locator_kind`, `locator_path` | Addressable location. `github` rows: `locator_kind = 'repo_path'`, `locator_path` = the file path. `rss` rows: `locator_kind = 'feed_item'`, `locator_path` = the post URL (per Module A contract v0.4; rss not emitted yet). |
| `span_index`, `span_total`, `span_heading_path` | Chunk position + heading breadcrumb (context for review/mapping). |
| `text` | The chunk text as harvested by Module A (canonical), for C to map to a CRE node. B's defensive sanitization is applied only to the LLM's classification input, so the stored `text` and `content_hash` stay canonical/stable. |
| `llm_label` | `KNOWLEDGE` or `UNCERTAIN` (B never writes `NOISE` here). |
| `confidence` | 0.0–1.0, B's LLM confidence. |
| `llm_reasoning` | Optional one-line rationale (debugging / Module D UI). |
| `created_at` | When B wrote the row. FIFO ordering. |
| `consumed_at` | NULL = pending. Module C sets `NOW()` after successful ingest. |

**Provenance invariant (queue boundary).** Module B is the **only** writer of `knowledge_queue`, and it inserts only rows built from a validated Module A `ChangeRecord` (Pydantic, discriminated on `source_type`, which rejects unknown source types). So B guarantees the branch-specific columns are populated per `source_type`: a `github` row always carries `source_repo` / `source_commit_sha` / `source_committed_at`; an `rss` row always carries `feed_url` / `post_guid`. The **database does not enforce this** — the branch columns are nullable and there are no CHECK constraints — so any *out-of-band* writer must uphold it. A row that violated it (e.g. an `rss` row with `post_guid` NULL) would make the read query's `source` synthesis below evaluate to `NULL`. (C's read validator currently enforces `github → source_repo + source_commit_sha` and `rss → feed_url`, but not `rss → post_guid`; tightening that, or adding DB CHECK constraints, is optional hardening — B never emits such a row.)

## Canonical read query

Module C reads the **full row** (all columns) — `DbKnowledgeSource` runs, in effect:

```sql
SELECT *            -- the whole row; C validates it via the KnowledgeQueueItem mirror at its C.0 boundary
FROM knowledge_queue
WHERE consumed_at IS NULL
  AND llm_label IN ('KNOWLEDGE', 'UNCERTAIN')   -- C consumes both; escalation to Module D (HITL) is C's own decision, not B's label
ORDER BY created_at, id
LIMIT :batch_size;
```

C needs the full row — `content_hash`, `chunk_id` / `artifact_id`, the `source_*` / `feed_*` / `locator_*` provenance, `span_*`, `llm_reasoning` — for boundary validation, provenance and traceability, not just a `{source, text, confidence}` slice. For **mapping**, C derives a source identity from the provenance columns (source-type-aware):

```sql
CASE source_type
  WHEN 'github' THEN source_repo || '@' || source_commit_sha || ':' || locator_path
  WHEN 'rss'    THEN feed_url || '#' || post_guid
END AS source        -- a value C computes from the row, not the SELECT projection
```

e.g. `{"source": "OWASP/ASVS@abc123:4.0/en/0x12-V3-Authentication.md", "text": "...", "confidence": 0.91}`.

## Consumption semantics

After mapping a batch, Module C MUST mark rows consumed:

```sql
UPDATE knowledge_queue SET consumed_at = NOW() WHERE id IN (:ids) AND consumed_at IS NULL;
```

- **Consumption is gated on durable persistence.** Module C stamps `consumed_at` **only after** the row's mapping output has been durably persisted, in the same transaction as the `consumed_at` update. Because `DbKnowledgeSource` selects only `consumed_at IS NULL` rows, an unstamped row is simply re-read next poll — so a failed delivery (or a row that errored mid-pipeline) is safely retried, and no row is marked done while its result "went nowhere." (`consumed_at` is entirely **Module C's** read-filter — Module B never reads it; B only inserts/dedups rows.) The downstream C→D handoff (Module C's `decision_queue`) is the authoritative sink and is specified in Module C's own contract — out of scope here.
- **Idempotency on retries:** un-marked rows keep `consumed_at IS NULL` and are picked up next poll. `UNIQUE(content_hash)` prevents B from inserting the same logical row twice.
- **Deduplication & provenance:** B writes with `INSERT ... ON CONFLICT (content_hash) DO NOTHING`, so identical normalized content — replayed in a later run, or harvested from a second source/mirror — collapses to **one** row: the **first-written** row and its provenance survive; later duplicates are silently skipped (counted as `deduped` in B's run summary, never an aborted batch). **Multi-origin provenance is therefore not retained in v1** — `knowledge_queue` records one origin per unique content. If every Module A origin must stay traceable, that is a future enhancement (e.g. a side table keyed by `content_hash`), out of scope for v1.
- **Ordering:** FIFO by `created_at`; use `id` as a tiebreaker for identical timestamps.
- **Concurrency — single consumer per run today.** The orchestrator serialises A→B→C and runs **one** Module C consumer per `pipeline_run_id`, and `DbKnowledgeSource` reads **without** row locking (`session.query(...).filter(consumed_at IS NULL, llm_label IN (…)).order_by(created_at, id)`) — safe for a single consumer. Running **multiple concurrent** consumers over the same rows is **not** safe as-is: two would select the same rows before either stamps `consumed_at`. To support that, each consumer must claim rows atomically — `SELECT ... WHERE consumed_at IS NULL ... FOR UPDATE SKIP LOCKED`, held through mapping + persistence + the `consumed_at` update in one transaction (this schema has only `consumed_at`, no claim-token column). **`DbKnowledgeSource` does not add `with_for_update(skip_locked=True)` today**, so row-locking is a required Module C change *before* concurrent consumers are deployed. (SQLite dev/CI supports neither `FOR UPDATE SKIP LOCKED` nor `NOW()` and is single-consumer regardless; the `NOW()` in the snippets is illustrative — C sets `consumed_at` via the ORM, backend-portable.)

## UNCERTAIN row policy

- B writes `llm_label = 'UNCERTAIN'` when the LLM returned UNCERTAIN (a genuine borderline chunk), or when classification failed — the batch errored or the response didn't parse (`confidence = 0.0`). B never drops these: recall-first means an UNCERTAIN chunk may still carry security signal.
- **Classification failures are terminal in v1 (first-write-wins).** A chunk written as `UNCERTAIN / 0.0` because the LLM call failed or its output didn't parse is kept as-is: `ON CONFLICT (content_hash) DO NOTHING` plus B marking the input row `processed` means a later run cannot replace it with a successful classification. This is intentional and safe under recall-first — the chunk still reaches C as `UNCERTAIN` (mapped, or routed to Module D), so nothing is lost; only its label/confidence is provisional. Forcing re-classification (e.g. after a model outage) is a deliberate operator action via a future `--allow_duplicate_hash` re-run (see the Module A contract) — out of scope for v1.
- **`llm_label` is B's confidence signal, not a routing directive.** Module C consumes **both** `KNOWLEDGE` and `UNCERTAIN` (`DbKnowledgeSource` filters `llm_label IN (READABLE_LABELS)`). Which chunks are auto-mapped vs. escalated to Module D's HITL review is **Module C's decision**, made by C's own boundary / cross-encoder / confidence logic. B's label does not gate what reaches Module D — it's just one input available to C.
- This keeps recall-first intact end to end: every non-NOISE chunk B produces is consumed and judged by C; nothing is stranded in the queue waiting on a label match.

## Stability guarantees

- **C reads the full row** and validates it via the `KnowledgeQueueItem` mirror (`extra="ignore"`, so B may **add** columns freely); existing columns won't be renamed or removed without a version bump.
- **The provenance/verdict columns C depends on** — `content_hash`, `chunk_id`, `artifact_id`, `pipeline_run_id`, `source_type` + the `source_*`/`feed_*`/`locator_*` set, `text`, `llm_label`, `confidence` — are stable for v1.0, even as B's internals evolve. The derived `{source, text, confidence}` mapping view is computed from these.
- **`consumed_at` is never reset** to NULL on an already-consumed row.

## Versioning

This contract is **v0.3 (draft)**. Becomes v1.0 when both contributors agree. semver applies as in the Module A contract.

## Test fixtures and integration

- Module B will produce a real-data fixture (a SQL dump of `knowledge_queue` from a pipeline run) so Module C can replay consumption end-to-end without A or B running live.
- First end-to-end live test: B fills the table on the shared dev Postgres + pgvector; C polls and maps a small batch.

## Out-of-scope for this contract

- How C maps chunks to CRE nodes (vector / cross-encoder / hybrid) — C's design space.
- Module D's HITL UI integration — separate contract (`module_d_contract.md`, future).
- GC of fully-consumed rows — neither B nor C deletes in v1.
- Read replicas / sharding — single-master Postgres for v1.
