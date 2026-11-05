# Module A — Harvest, Normalize & Chunk

**Owner:** Backend / connectors  
**Produces:** `IngestBatch` / `ArtifactIngestEvent` → **Ingest Bucket**  
**Consumes:** `sources.yaml` config + **artifact registry** (out of band)

## Responsibility

1. **Connect** to sources via adapters (`github`, `rss`, `url`, …).
2. **Backfill** artifacts never seen before (full resource read).
3. **Incrementally** harvest known artifacts (diff, poll, content-hash).
4. **Normalize** HTML/Markdown to clean text.
5. **Chunk** into stable `IngestChunk` units for Module B.

Module B receives **chunks**, not raw git diffs. Your harvester can use any library you like to read files; the handoff is the JSON types below.

## Config (input, not handover JSON)

```yaml
# sources.yaml (illustrative)
schema_version: "0.2.0"
sources:
  - type: github
    repo: OWASP/ASVS
    default_branch: master
    paths_include: ["**/*.md"]
    paths_exclude: ["**/package-lock.json", "**/CNAME"]
  - type: rss
    url: https://example.org/feed.xml
chunking:
  strategy: markdown_heading  # markdown_heading | html_readability | fixed_size
  max_chars: 4000
  overlap_chars: 200
```

## Artifact registry (internal to A)

Tracks `artifact_id`, last `content_hash`, last `observed_at`, last `commit_sha` (if git). Drives backfill vs incremental:

| Registry state | A behavior |
| --- | --- |
| Unknown `artifact_id` | **Backfill** — full read, `event_type: discovered` |
| Known, hash/commit changed | **Incremental** — delta or full re-chunk |
| Known, unchanged | Skip (no emit) |

## Handover out (A → B)

### Transport

| Format | Use |
| --- | --- |
| `ingest-batch.json` | Full run metadata + `events[]` |
| `ingest-chunks.jsonl` | **Preferred for B** — one `IngestChunkRecord` per line |

Module B processes **one `IngestChunkRecord` per `chunk_id`**.

### `IngestBatch`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | e.g. `0.2.0` |
| `pipeline_run_id` | string | yes | Run identifier |
| `harvested_at` | string (date-time) | yes | When A finished |
| `harvest_mode` | `backfill` \| `incremental` \| `mixed` | yes | Dominant mode for this run |
| `watermark_from` | string (date-time) | no | Incremental lower bound |
| `watermark_to` | string (date-time) | no | Incremental upper bound |
| `events` | `ArtifactIngestEvent[]` | yes | One per changed artifact |

### `ArtifactIngestEvent`

One logical resource (file, page, feed entry) in a single harvest pass.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | |
| `event_id` | string | yes | Unique for this harvest pass |
| `artifact_id` | string | yes | Stable across runs (hash of source + locator) |
| `pipeline_run_id` | string | yes | |
| `observed_at` | string (date-time) | yes | When A emitted this event |
| `harvest_mode` | `backfill` \| `incremental` | yes | How this artifact was read |
| `event_type` | `discovered` \| `modified` \| `deleted` | yes | Registry semantics |
| `source` | `SourceRef` | yes | Provenance |
| `locator` | `Locator` | yes | Where in the source |
| `artifact` | `ArtifactMeta` | yes | Resource metadata |
| `chunks` | `IngestChunk[]` | yes if not deleted | Normalized chunks |
| `harvest` | `HarvestMeta` | yes | Adapter + chunking audit |

#### `Locator`

| Field | Type | Required |
| --- | --- | --- |
| `kind` | `repo_path` \| `url` \| `feed_item` | yes |
| `id` | string | yes | Canonical key (path, URL, or feed GUID) |
| `path` | string | if `repo_path` |
| `url` | string | if `url` or `feed_item` |
| `title` | string | no |

#### `ArtifactMeta`

Resource-level facts about the whole file or page (similar to what you might stash in a LlamaIndex `Document.metadata` dict — filename, mime type, etc.).

| Field | Type | Required |
| --- | --- | --- |
| `title` | string | no |
| `mime` | string | no | e.g. `text/markdown`, `text/html` |
| `content_hash` | string | yes | `sha256:` of normalized full body |
| `language` | string | no | BCP-47, default `en` |
| `change_type` | `added` \| `modified` \| `deleted` \| `renamed` | no | VCS hint |
| `previous_locator_id` | string | no | If renamed |

#### `IngestChunk`

The **unit Module B classifies** (relevance filter). One artifact → many chunks (same mental model as one LlamaIndex `Document` split into `TextNode`s).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `chunk_id` | string | yes | Stable under `artifact_id` (hash of artifact + span) |
| `text` | string | yes | Normalized plain text for this chunk — like a `TextNode.text` if you have seen LlamaIndex tutorials |
| `char_count` | integer | yes | |
| `span` | `ChunkSpan` | yes | Position within artifact |
| `delta` | `ChunkDelta` | no | Incremental: text before change |

#### `ChunkSpan`

| Field | Type | Required |
| --- | --- | --- |
| `index` | integer | yes | 0-based chunk index |
| `total` | integer | yes | Chunks in this event |
| `heading_path` | string[] | no | e.g. `["Authentication", "JWT"]` |
| `start_char_idx` | integer | no | Optional; many splitters (including LlamaIndex node parsers) already expose start/end character indices |
| `end_char_idx` | integer | no | Optional; pair with `start_char_idx` |
| `start_line` | integer | no |
| `end_line` | integer | no |

#### `ChunkDelta`

Only for `harvest_mode: incremental` and `event_type: modified`.

| Field | Type | Required |
| --- | --- | --- |
| `text_before` | string | no | Prior chunk text if known |

#### `HarvestMeta`

| Field | Type | Required |
| --- | --- | --- |
| `adapter` | string | yes | e.g. `github`, `rss`, `http` |
| `fetcher` | string | yes | e.g. `oie-harvester/0.2.0` |
| `registry_seen_before` | boolean | yes |
| `excluded_by_path_rule` | boolean | yes |
| `chunking` | object | yes | `{ "strategy", "max_chars", "overlap_chars" }` |
| `llm_diff_judge` | object | no | `{ "meaning_changed", "model" }` |

## Logical API (future)

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/internal/oie/v0/ingest/runs` | Start run (`?mode=backfill\|incremental`) |
| `GET` | `/internal/oie/v0/ingest/runs/{id}/chunks` | Paginated `IngestChunk` stream |

MVP: `ingest-chunks.jsonl` on object storage.

## Example `ArtifactIngestEvent` (backfill)

```json
{
  "schema_version": "0.2.0",
  "event_id": "evt_20260201_00001",
  "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
  "pipeline_run_id": "20260201T020000Z",
  "observed_at": "2026-02-01T02:18:00Z",
  "harvest_mode": "backfill",
  "event_type": "discovered",
  "source": {
    "type": "github",
    "repo": "OWASP/ASVS",
    "commit_sha": "abc123def456",
    "committed_at": "2026-02-01T01:12:00Z"
  },
  "locator": {
    "kind": "repo_path",
    "id": "4.0/en/0x12-V3-Authentication.md",
    "path": "4.0/en/0x12-V3-Authentication.md",
    "title": "V3 Authentication"
  },
  "artifact": {
    "mime": "text/markdown",
    "content_hash": "sha256:…",
    "language": "en",
    "change_type": "added"
  },
  "chunks": [
    {
      "chunk_id": "chk:art:OWASP/ASVS:…:0",
      "text": "Verify that JWTs are validated on every request, including signature, exp, and aud claims.",
      "char_count": 98,
      "span": { "index": 0, "total": 3, "heading_path": ["Authentication", "JWT"] }
    }
  ],
  "harvest": {
    "adapter": "github",
    "fetcher": "oie-harvester/0.2.0",
    "registry_seen_before": false,
    "excluded_by_path_rule": false,
    "chunking": { "strategy": "markdown_heading", "max_chars": 4000, "overlap_chars": 200 }
  }
}
```

## Example JSONL line (incremental chunk)

```json
{
  "schema_version": "0.2.0",
  "chunk_id": "chk:art:OWASP/ASVS:…:2",
  "event_id": "evt_20260201_00042",
  "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
  "pipeline_run_id": "20260201T020000Z",
  "harvest_mode": "incremental",
  "event_type": "modified",
  "source": { "type": "github", "repo": "OWASP/ASVS", "commit_sha": "def789", "committed_at": "2026-02-02T01:00:00Z" },
  "locator": { "kind": "repo_path", "id": "4.0/en/0x12-V3-Authentication.md", "path": "4.0/en/0x12-V3-Authentication.md" },
  "artifact": { "content_hash": "sha256:…", "mime": "text/markdown" },
  "chunk": {
    "chunk_id": "chk:art:OWASP/ASVS:…:2",
    "text": "Verify that JWTs are validated on every request, including signature, exp, and aud claims.",
    "char_count": 98,
    "span": { "index": 2, "total": 3, "heading_path": ["Authentication", "JWT"] },
    "delta": { "text_before": "Verify that JWTs are validated on every request." }
  }
}
```

## Schema

- [schemas/ingest-batch.json](./schemas/ingest-batch.json)
- [schemas/artifact-ingest-event.json](./schemas/artifact-ingest-event.json)
- [schemas/ingest-chunk.json](./schemas/ingest-chunk.json)
- [schemas/ingest-chunk-record.json](./schemas/ingest-chunk-record.json) (JSONL line)
- [schemas/locator.json](./schemas/locator.json)

**Deprecated (0.1.0):** `raw-change-batch.json`, `raw-change-item.json` — use ingest types above.
