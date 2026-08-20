# Module A → Module B Input Contract

**Audience:** the GSoC 2026 contributor implementing Module A (Information Harvesting — nightly cron job that fetches content from OWASP repos and feeds). **Status:** draft **v0.4** (2026-08-16). Reconciled against the orchestrated-pipeline hand-off (DB table, not a JSONL file) and Module C's shipped consumer (`feed_item` rss locator kind). Pending review by mentors and the Module A contributor.

This document specifies the format Module A emits so that Module B (Noise/Relevance Filter) can consume it. Module B is the only downstream consumer in v1; any change to this format is a breaking change for B.

---

## Changelog (v0.3 → v0.4)

- **Delivery moved from a JSONL file to a DB table.** The orchestrated pipeline supersedes the earlier "JSONL file via `cre.py --filter_changes <path>`" transport. Module A now writes each record as a row in the shared Postgres `harvest_input` table (JSONB `payload` + top-level `pipeline_run_id` + `status`); Module B reads the pending rows for a run. The `--filter_changes` CLI was never built; Module B's entry point is `cre.py --run_noise_filter --run_id <id>`.
- **rss `locator.kind` reserved value is `feed_item`** (was `feed_post`), aligning with Module C's shipped consumer (PR #1011), which addresses rss rows by `locator_kind = "feed_item"`. github rows are unchanged (`repo_path`). rss is still not emitted; this only fixes the reserved name so all three modules agree.

## Changelog (v0.2 → v0.3)

Driven by reconciliation with Module A's actual mock output. The shape is significantly different from what the v0.2 draft anticipated.

- **Structural shift:** record fields are no longer flat. Three nested objects now exist: `source` (provenance), `span` (chunk position within parent artifact), `locator` (addressable identity).
- **New top-level fields:** `schema_version`, `chunk_id`, `pipeline_run_id`.
- **Renames / relocations:**
  - `chunk_text` → `text`
  - `source_type` → `source.type`
  - `repo` → `source.repo`
  - `commit_sha` → `source.commit_sha`
  - `author_date` → `source.committed_at`
  - `file_path` → `locator.path` (also `locator.id` mirrors for now)
  - `chunk_index` → `span.index`
- **New `span` payload:** beyond `index` (which `chunk_index` already provided), `span` also carries `total`, `heading_path` (the markdown heading breadcrumb), `start_char_idx`/`end_char_idx`, `start_line`/`end_line`.
- **`content_hash` removed.** Module A does not emit a content hash. **Module B computes its own** by applying the v0.2 normalization rules (NFC, line endings, whitespace, code-fence preservation) and SHA-256-ing the result. Used by B as the `knowledge_queue` dedup key.
- **`commit_message` removed.** Module A does not emit commit messages. Module B's LLM prompt now uses `span.heading_path` as the semantic context signal instead (e.g. `["Authentication", "JWT"]` is a richer disambiguator than a commit message).
- **`source.type = "rss"` is reserved.** Mock data is github-only; the discriminated-union schema accepts RSS shape so we're ready when Module A emits feed records.
- **Mock note:** the mock data uses placeholder values like `"abc123"` for `commit_sha` and `"…"` (encoded as corrupted UTF-8 `â¦` in the source) for path segments inside `chunk_id`. Production must emit real 40-char SHAs and clean UTF-8.

---

## Transport

- **Format:** one JSON object per chunk — the record described below — stored verbatim as the JSONB `payload` of a `harvest_input` row. (Module B's local test fixtures still keep the same records as JSONL; the on-the-wire shape of a single record is identical either way.)
- **Delivery:** Module A writes each record as a row in the shared Postgres **`harvest_input`** table — columns `payload` (JSONB, the record), `pipeline_run_id` (top-level, run-scoping), `status` (`pending` → set by A; `processed`/`error` → set by B), plus `id`/`created_at`. Module B reads that run's pending rows (`cre.py --run_noise_filter --run_id <id>`), classifies, and writes keepers to `knowledge_queue`. See `module_b_runbook.md` for the operational how-to. *(The earlier "JSONL file via `cre.py --filter_changes`" delivery is superseded and was never implemented.)*
- **Run-id consistency (required):** a row's top-level `harvest_input.pipeline_run_id` **must equal** the `pipeline_run_id` inside its JSONB `payload`. Module B scopes a run by the top-level column (`WHERE pipeline_run_id = :run_id`) but copies the *payload's* `pipeline_run_id` onto the `knowledge_queue` row. If the two differ, a chunk is processed under one run yet emitted under another. Module A MUST write identical values (equivalently, Module B may reject rows where they disagree).
- **Future (out of scope for v1):** object-storage URL (S3/MinIO) for large or out-of-band payloads.
- **Record size:** governed by Module A's chunking config (default `max_chars=4000`). Module B truncates internally at 1500 chars before sending to the LLM.

## Required fields (top level)

| Field | Type | Constraints |
|---|---|---|
| `schema_version` | string | E.g. `"0.2.0"`. Pinned by Module A; B reads but does not validate version semantics. |
| `chunk_id` | string | Module-A-stable identifier. Format observed in mock: `chk:<artifact_id>:<chunk_index>` (i.e. `chk:art:OWASP/<repo>:<path>:<idx>`). |
| `artifact_id` | string | Identifier for the parent document. Format observed in mock: `art:<repo>:<path>`. Stable across chunks of the same artifact. |
| `pipeline_run_id` | string | Identifier for the Module A pipeline execution that produced this record. E.g. `"20260201T020000Z"`. Used by B for audit / replay grouping. |
| `text` | string | The normalized chunk content. Markdown markers (`#`, `**`, code fences) preserved; HTML stripped; whitespace collapsed in prose but preserved inside code fences (`` ``` ``…`` ``` ``) and `<pre>` blocks. |
| `span` | object | Position metadata. See below. |
| `source` | object | Provenance discriminator (`source.type`). See below. |
| `locator` | object | Addressable identity. See below. |

## Required `span` payload

| Field | Type | Constraints |
|---|---|---|
| `index` | int ≥ 0 | Zero-based chunk index within the parent artifact. |
| `total` | int ≥ 1 | Total chunks Module A produced from this artifact. |
| `heading_path` | array of strings | Breadcrumb of enclosing markdown headings (e.g. `["Authentication", "JWT"]`). Empty array if the chunk precedes all headings. Used as a semantic signal in B's LLM prompt. |
| `start_char_idx` | int ≥ 0 (optional) | Character index of chunk start in the normalized artifact text. |
| `end_char_idx` | int ≥ 0 (optional) | Character index of chunk end (exclusive). |
| `start_line` | int ≥ 0 (optional) | 1-based line number of chunk start in the normalized artifact. |
| `end_line` | int ≥ 0 (optional) | 1-based line number of chunk end. |

## Required `source` payload — discriminated union

`source.type` discriminates between provenance shapes.

**When `source.type = "github"`:**

| Field | Type | Constraints |
|---|---|---|
| `type` | string | Literal `"github"`. |
| `repo` | string | Format `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`. Allows OWASP dots/dashes. |
| `commit_sha` | string | Production: 40-char hex SHA-1. Mock: 6+ char placeholders accepted. |
| `committed_at` | string | ISO-8601 timestamp. |

**When `source.type = "rss"` (reserved, not yet emitted):**

| Field | Type | Constraints |
|---|---|---|
| `type` | string | Literal `"rss"`. |
| `feed_url` | string | The canonical feed URL Module A subscribed to. |
| `post_guid` | string | The `<guid>` or `<id>` of the post within the feed. |
| `post_published_at` | string (optional) | ISO-8601 timestamp. |

## Required `locator` payload

| Field | Type | Constraints |
|---|---|---|
| `kind` | string | Scheme. `"repo_path"` for github sources today. Reserved: `"feed_item"` for RSS (matches Module C's consumer, PR #1011). |
| `id` | string | Unique identity within the scheme. For `repo_path`: the file path. For `feed_item`: the post URL. |
| `path` | string | For `repo_path`: convenience duplicate of `id` (`id == path`), used by B's regex path filter. For `feed_item`: **the post URL** — Module C requires a parseable URL for a `feed_item` locator (its consumer rejects a `feed_item` without one), so `path` carries the item URL (stored as `knowledge_queue.locator_path`). |

## Example record (github source — mock-shaped)

```json
{
  "schema_version": "0.2.0",
  "chunk_id": "chk:art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md:0",
  "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
  "pipeline_run_id": "20260201T020000Z",
  "text": "Authentication should use MFA",
  "span": {
    "index": 0,
    "total": 3,
    "heading_path": ["Authentication", "JWT"],
    "start_char_idx": 0,
    "end_char_idx": 98,
    "start_line": 10,
    "end_line": 12
  },
  "source": {
    "type": "github",
    "repo": "OWASP/ASVS",
    "commit_sha": "abc123",
    "committed_at": "2026-02-01T01:00:00Z"
  },
  "locator": {
    "kind": "repo_path",
    "id": "4.0/en/0x12-V3-Authentication.md",
    "path": "4.0/en/0x12-V3-Authentication.md"
  }
}
```

## Content hashing — Module B's responsibility

Module A does **not** emit `content_hash`. Module B computes one on ingest in `application/utils/noise_filter/hashing.py`:

1. Apply v0.2 normalization rules to `text`:
   - Unicode NFC
   - CRLF / CR → LF
   - Trailing whitespace per line stripped
   - Leading/trailing blank lines stripped
   - Runs of spaces/tabs in prose collapsed to one space
   - Whitespace inside fenced code blocks (`` ``` `` … `` ``` ``) and `<pre>` blocks preserved verbatim
2. `content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()`

The hash becomes the `UniqueConstraint` key on `knowledge_queue` — re-feeding identical normalized content (e.g. mirrored docs, replayed pipeline runs) collapses to one queue row.

**Future:** if Module A starts emitting `content_hash`, B switches via `CRE_NOISE_FILTER_TRUST_A_HASH=true` to skip recomputation. Until then, B is self-sufficient.

## Normalization ownership

- **Module A owns "normalize for chunking":** semantic chunking, heading-path tracking, char/line offsets.
- **Module B owns "normalize for hashing" + "defensive sanitization":** the rules above (for `content_hash`), plus TRACT-style sanitize.py (zero-width chars, PDF ligatures, hyphenation rejoin) as Stage 1.5 of B's pipeline.

If Module A's own normalization differs from B's (e.g. A doesn't collapse prose whitespace), B's hash still works — B always normalizes before hashing. The two normalizations don't need to agree.

## Path-filtering ownership

- **Module A owns coarse exclusion:** the `paths_exclude` globs in its source config (e.g. `["**/package-lock.json", "**/CNAME"]`). These never reach B.
- **Module B owns fine-grained noise filtering:** `application/utils/noise_filter/noise_patterns.yaml`. Catches things A's source config didn't anticipate.

If both modules block the same path, that's fine — B silently no-ops. The two lists drift independently.

## Stability guarantees

- **Module B reads only the fields listed above** (and ignores everything else). Extra fields Module A adds — `pr_number`, `author`, `tags`, `supersedes_artifact_id`, etc. — are silently accepted (`extra="ignore"` on B's Pydantic models). Safe to extend.
- **Renaming or removing any required field is breaking.** Requires a contract version bump and coordinated changes in `application/utils/noise_filter/schemas.py`.
- **Changing the semantics of a field is breaking** even if the name stays the same. Example: switching `locator.path` to absolute paths would break B's regex pre-filter.

## Idempotency on Module B's side

Module B's `knowledge_queue` uses `UniqueConstraint(content_hash)` as the dedup key. Consequences:
- Re-feeding the same normalized content is a no-op.
- The same content reaching B via two different sources collapses to one row.
- To force re-classification (e.g. prompt changed), Module B will provide an `--allow_duplicate_hash` flag on the CLI. Out of scope for v1.

## Versioning

This contract is **v0.4** (draft). When ratified, becomes v1.0. semver applies:
- v1.X = additive, non-breaking field additions.
- v2.0 = breaking changes.

The version applies to *this contract*, not to Module A's release cadence.

## JSON Schema artifact

The machine-readable schema is generated from Module B's Pydantic models and committed at:

```text
docs/gsoc_2026_module_b/module_a_contract.schema.json
```

Both modules SHOULD validate against it in CI. Module B's Pydantic model (`application/utils/noise_filter/schemas.ChangeRecord`) is the canonical source; the JSON Schema file is derived via `ChangeRecord.model_json_schema()`.

## Test fixtures

Module B keeps fixtures at:

```text
application/tests/noise_filter/fixtures/
├── module_a_mock.jsonl          # Module A's 20-record mock (canonical, what A actually emits)
├── candidate_commits.json       # B's own stand-in harvest of ~100 OWASP commits in Module A's shape
└── labeled_data.json            # candidate_commits.json + KNOWLEDGE/NOISE/UNCERTAIN labels
```

Module A contributors are welcome to add fixtures here as PRs — small files (≤30 records each) covering edge cases (PDF-extracted text, HTML-derived chunks, RSS posts) help Module B's regex and prompt iteration.

## Out-of-scope for this contract

- How Module A produces these records (GitHub API vs `git log` vs webhook vs feed poll).
- Where Module A stores raw artifacts before chunking.
- Failure handling on the Module A side (rate-limit retries, partial commits).
- Authentication / API keys (Module A's concern).
- Module A's source-config schema (`schema_version`, `sources`, `chunking`) — that's internal to A.
