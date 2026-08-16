# Module B → Module C Output Contract

**Audience:** the GSoC 2026 contributor implementing Module C (The Librarian — vector + cross-encoder mapping of filtered knowledge chunks to existing CRE nodes). **Status:** draft **v0.3** (2026-08-16). Reconciled with the orchestrated-pipeline hand-off and with Module C's shipped consumer (PR #1011), which now mirrors this table column-for-column.

This document specifies how Module C reads Module B's output. Module B produces; Module C consumes; Module D's HITL UI may also read for review.

---

## Changelog (v0.2 → v0.3)

- **Module C consumes both `KNOWLEDGE` and `UNCERTAIN`.** The canonical read query now selects `llm_label IN ('KNOWLEDGE', 'UNCERTAIN')` (was `= 'KNOWLEDGE'`). B's `llm_label` is a confidence signal, not a routing directive: C consumes every non-NOISE row and decides internally which chunks need Module D's HITL review. This keeps recall-first intact end to end — no security chunk is stranded in the queue for a label that has no downstream consumer.
- **Verified against Module C's shipped consumer (PR #1011).** C's `KnowledgeQueueItem` now mirrors this table column-for-column (all 23 columns, both `github` and `rss` provenance branches), and stamps `consumed_at` as its only write. (#1011 as shipped filters `llm_label = 'KNOWLEDGE'`; per the bullet above, its C0 read filter should be updated to `IN ('KNOWLEDGE', 'UNCERTAIN')`.)
- **`source_committed_at` type corrected to `String`.** Module B stores it as an ISO-8601 **string** (the value Module A emits, unparsed), not a `DateTime`. Module C parses it to a datetime on read (Pydantic coercion) — no conflict, but the storage type in this contract now matches Module B's actual model/migration.

## Changelog (v0.1 → v0.2)

- **Orchestrated pipeline:** B is now invoked by the daily **orchestrator** (not a manual CLI run). B reads Module A's chunks from a Postgres table, classifies, writes keepers to `knowledge_queue`, and signals the orchestrator "done"; the orchestrator then calls C.
- **Schema aligned to Module A contract v0.3:** provenance columns now mirror A's nested `source` / `span` / `locator` record (confirmed unchanged by A on 2026-07-16), instead of the old flat `source_repo` / `source_path` / `source_commit_sha`.
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

```python
class KnowledgeQueueItem(BaseModel):
    __tablename__ = "knowledge_queue"
    id             = sqla.Column(sqla.String, primary_key=True, default=generate_uuid)
    content_hash   = sqla.Column(sqla.String(64), nullable=False)   # B-computed dedup key
    # provenance / traceability (from Module A's v0.3 record)
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
| `locator_kind`, `locator_path` | Addressable location (`repo_path` → file path today). |
| `span_index`, `span_total`, `span_heading_path` | Chunk position + heading breadcrumb (context for review/mapping). |
| `text` | The chunk text as harvested by Module A (canonical), for C to map to a CRE node. B's defensive sanitization is applied only to the LLM's classification input, so the stored `text` and `content_hash` stay canonical/stable. |
| `llm_label` | `KNOWLEDGE` or `UNCERTAIN` (B never writes `NOISE` here). |
| `confidence` | 0.0–1.0, B's LLM confidence. |
| `llm_reasoning` | Optional one-line rationale (debugging / Module D UI). |
| `created_at` | When B wrote the row. FIFO ordering. |
| `consumed_at` | NULL = pending. Module C sets `NOW()` after successful ingest. |

## Canonical read query (source-type-aware)

```sql
SELECT
    id,
    CASE source_type
      WHEN 'github' THEN source_repo || '@' || source_commit_sha || ':' || locator_path
      WHEN 'rss'    THEN feed_url || '#' || post_guid
    END AS source,
    text,
    confidence
FROM knowledge_queue
WHERE consumed_at IS NULL
  AND llm_label IN ('KNOWLEDGE', 'UNCERTAIN')   -- C consumes both; escalation to Module D (HITL) is C's own decision, not B's label
ORDER BY created_at
LIMIT :batch_size;
```

The synthesized `source` gives the frozen `{source, text, confidence}` payload C originally requested:

```json
{"source": "OWASP/ASVS@abc123:4.0/en/0x12-V3-Authentication.md", "text": "...", "confidence": 0.91}
```

## Consumption semantics

After mapping a batch, Module C MUST mark rows consumed:

```sql
UPDATE knowledge_queue SET consumed_at = NOW() WHERE id IN (:ids);
```

- **Idempotency on retries:** un-marked rows keep `consumed_at IS NULL` and are picked up next poll. `UNIQUE(content_hash)` prevents B from inserting the same logical row twice.
- **Ordering:** FIFO by `created_at`; use `id` as a tiebreaker for identical timestamps.
- **Concurrent consumers:** `consumed_at IS NULL` + row-level `UPDATE ... WHERE consumed_at IS NULL` is safe; for multi-consumer, use `SELECT ... FOR UPDATE SKIP LOCKED`.

## UNCERTAIN row policy

- B writes `llm_label = 'UNCERTAIN'` when the LLM returned UNCERTAIN (a genuine borderline chunk), or when classification failed — the batch errored or the response didn't parse (`confidence = 0.0`). B never drops these: recall-first means an UNCERTAIN chunk may still carry security signal.
- **`llm_label` is B's confidence signal, not a routing directive.** Module C consumes **both** `KNOWLEDGE` and `UNCERTAIN` (`llm_label IN ('KNOWLEDGE', 'UNCERTAIN')`). Which chunks are auto-mapped vs. escalated to Module D's HITL review is **Module C's decision**, made by C's own boundary / cross-encoder / confidence logic. B's label does not gate what reaches Module D — it's just one input available to C.
- This keeps recall-first intact end to end: every non-NOISE chunk B produces is consumed and judged by C; nothing is stranded in the queue waiting on a label match.

## Stability guarantees

- **C reads only the columns in the canonical query.** B may add columns; existing ones won't be renamed/removed without a version bump.
- **The `{source, text, confidence}` projection is frozen for v1.0**, even if B's internal columns evolve.
- **`consumed_at` is never reset** to NULL on an already-consumed row.

## Versioning

This contract is **v0.2 (draft)**. Becomes v1.0 when both contributors agree. semver applies as in the Module A contract.

## Test fixtures and integration

- Module B will produce a real-data fixture (a SQL dump of `knowledge_queue` from a pipeline run) so Module C can replay consumption end-to-end without A or B running live.
- First end-to-end live test: B fills the table on the shared dev Postgres + pgvector; C polls and maps a small batch.

## Out-of-scope for this contract

- How C maps chunks to CRE nodes (vector / cross-encoder / hybrid) — C's design space.
- Module D's HITL UI integration — separate contract (`module_d_contract.md`, future).
- GC of fully-consumed rows — neither B nor C deletes in v1.
- Read replicas / sharding — single-master Postgres for v1.
