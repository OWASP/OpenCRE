# Module B — Noise / Relevance Filter

**Owner:** Prompt / AI engineering  
**Consumes:** `IngestChunkRecord` (from Ingest Bucket, JSONL)  
**Produces:** `KnowledgeItem` → **Knowledge Queue** (one per `chunk_id`)

## Responsibility

Cheap rejection (regex/path), then LLM gate: “Is this security knowledge?” Module A already normalized and chunked text; B does **not** split HTML/Markdown.

## Handover in (A → B)

[Module A](./module-a-harvesting.md) emits `ingest-chunks.jsonl` — one `IngestChunkRecord` per line. B reads `chunk.text` (and optional `chunk.delta.text_before` for context).

## Handover out (B → C)

### `KnowledgeItem`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | e.g. `0.2.0` |
| `chunk_id` | string | yes | From A |
| `artifact_id` | string | yes | From A |
| `event_id` | string | yes | From A |
| `pipeline_run_id` | string | yes | |
| `filtered_at` | string (date-time) | yes | |
| `status` | `accepted` \| `rejected` \| `deferred` | yes | |
| `source` | `SourceRef` | yes | Copy from A |
| `locator` | `Locator` | yes | Copy from A |
| `content` | `KnowledgeContent` | if accepted | Text for C |
| `filter` | `FilterResult` | yes | Audit for golden dataset |
| `rejection` | `RejectionDetail` | if rejected | |

#### `KnowledgeContent`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `text` | string | yes | From `chunk.text` — still plain text, same role as in a LlamaIndex node |
| `title_hint` | string | no | `locator.title` or first heading in `span.heading_path` |
| `keywords` | string[] | no | Optional LLM-extracted terms |
| `language` | string | no | From `artifact.language` |

#### `FilterResult` / `FilterStage` / `RejectionDetail`

Unchanged from prior spec — see [schemas/knowledge-item.json](./schemas/knowledge-item.json).

## Example `KnowledgeItem` (accepted)

```json
{
  "schema_version": "0.2.0",
  "chunk_id": "chk:art:OWASP/ASVS:…:2",
  "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
  "event_id": "evt_20260201_00042",
  "pipeline_run_id": "20260201T020000Z",
  "filtered_at": "2026-02-01T02:25:00Z",
  "status": "accepted",
  "source": { "type": "github", "repo": "OWASP/ASVS", "commit_sha": "def789", "committed_at": "2026-02-02T01:00:00Z" },
  "locator": { "kind": "repo_path", "id": "4.0/en/0x12-V3-Authentication.md", "path": "4.0/en/0x12-V3-Authentication.md", "title": "JWT validation" },
  "content": {
    "text": "Verify that JWTs are validated on every request, including signature, exp, and aud claims.",
    "title_hint": "JWT validation",
    "keywords": ["JWT", "authentication"]
  },
  "filter": {
    "stages": [
      { "name": "regex_path", "passed": true },
      { "name": "llm_relevance", "passed": true, "model": "gpt-4o-mini", "latency_ms": 320 }
    ],
    "is_security_knowledge": true,
    "security_summary": "JWT validation must check signature and standard claims.",
    "confidence": 0.96
  }
}
```

## Schema

- [schemas/knowledge-item.json](./schemas/knowledge-item.json)
