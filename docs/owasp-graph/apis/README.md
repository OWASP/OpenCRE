# OIE module handover APIs

Draft contracts for data passed between the four OIE modules. These are **internal pipeline APIs**, not the public OpenCRE REST API. Shapes follow the [RFC](../designs/owasp-pane-of-glass.md) module boundaries.

## Conventions

| Rule | Detail |
| --- | --- |
| **Format** | JSON documents; batches may be JSONL (one envelope per line) |
| **Versioning** | Every envelope includes `schema_version` (semver string, e.g. `0.2.0`) |
| **IDs** | `artifact_id` = stable resource; `chunk_id` = stable text unit for B/C; `event_id` = one harvest pass |
| **Correlation** | `pipeline_run_id` groups all items from one scheduled run |
| **Time** | ISO-8601 UTC |
| **Text** | Module A emits **normalized, chunked** plain text |
| **Idempotency** | Consumers tolerate duplicate `chunk_id`; registry + content hash prevent re-emit |

## Boundaries

| From → To | Bucket / queue name (MVP) | Envelope type | Doc |
| --- | --- | --- | --- |
| **A → B** | `ingest-bucket/` | `IngestChunkRecord` (JSONL) or `IngestBatch` | [module-a-harvesting.md](./module-a-harvesting.md) |
| **B → C** | `knowledge-queue/` | `KnowledgeItem` (per `chunk_id`) | [module-b-filter.md](./module-b-filter.md) |
| **C → D** | `review-queue/` | `ReviewItem` | [module-c-librarian.md](./module-c-librarian.md) |
| **C → OpenCRE** | (existing ingest path) | `LinkProposal` | [module-c-librarian.md](./module-c-librarian.md) |
| **D → (feedback)** | `corrections.jsonl` | `HumanDecision` | [module-d-hitl.md](./module-d-hitl.md) |

## MVP transport (not normative)

1. **Files** — `s3://…/oie/{pipeline_run_id}/ingest-chunks.jsonl`
2. **Pull API** — `GET /internal/oie/v0/ingest/runs/{id}/chunks` (future)
3. **Queue** — topic per boundary with the same JSON body

## Shared types

JSON Schemas live in [schemas/](./schemas/).

```json
{
  "schema_version": "0.2.0",
  "chunk_id": "chk:art:OWASP/ASVS:…:0",
  "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
  "event_id": "evt_20260201_00001",
  "pipeline_run_id": "20260201T020000Z",
  "source": { "type": "github", "repo": "OWASP/ASVS", "commit_sha": "abc123", "committed_at": "2026-02-01T01:00:00Z" },
  "locator": { "kind": "repo_path", "id": "4.0/en/0x12-V3-Authentication.md", "path": "4.0/en/0x12-V3-Authentication.md" }
}
```

**Deprecated 0.1.0:** `change_id` + `RawChangeItem` — use `chunk_id` + `IngestChunkRecord`.

## Status codes (logical, all modules)

| Code | Meaning |
| --- | --- |
| `accepted` | Passed this stage; forwarded |
| `rejected` | Dropped intentionally |
| `deferred` | Held for retry or human |
| `linked` | Module C auto-linked above threshold |
| `review_required` | Module C below threshold or policy flag |
| `corrected` | Module D human override recorded |

## Module docs

- [Module A — Harvest & chunk](./module-a-harvesting.md)
- [Module B — Filter](./module-b-filter.md)
- [Module C — Librarian](./module-c-librarian.md)
- [Module D — HITL](./module-d-hitl.md)
