# Module C — The Librarian

**Owner:** Data science / embeddings  
**Consumes:** `KnowledgeItem` (Knowledge Queue)  
**Produces:** `LinkProposal` (auto-link path) and/or `ReviewItem` (HITL path)

## Responsibility

Retrieve CRE candidates (vector + optional BM25), re-rank with cross-encoder, detect content updates, apply threshold (`0.8` per RFC), emit links or human review.

## Handover in (B → C)

`KnowledgeItem` with `status: accepted` only.

## Handover out — auto link (C → OpenCRE ingest)

### `LinkProposal`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | |
| `chunk_id` | string | yes | From B |
| `artifact_id` | string | yes | From B |
| `pipeline_run_id` | string | yes | |
| `classified_at` | string (date-time) | yes | |
| `status` | `linked` | yes | |
| `knowledge` | `KnowledgeSnapshot` | yes | Subset of B content + ids |
| `retrieval` | `RetrievalAudit` | yes | Candidates and scores |
| `links` | `ProposedLink[]` | yes | One or more CRE targets |
| `update_detection` | `UpdateDetection` | yes | New vs update vs adversarial flag |

#### `KnowledgeSnapshot`

| Field | Type | Required |
| --- | --- | --- |
| `text` | string | yes |
| `source` | `SourceRef` | yes |
| `locator` | `Locator` | yes |
| `security_summary` | string | no |

#### `RetrievalAudit`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `retriever` | string | yes | e.g. `pgvector+cross-encoder/0.1.0` |
| `candidates` | `CreCandidate[]` | yes | Top-N (e.g. 20) before re-rank |
| `reranked` | `CreCandidate[]` | yes | Top-K after cross-encoder (e.g. 5) |
| `threshold` | number | yes | e.g. `0.8` |

#### `CreCandidate`

| Field | Type | Required |
| --- | --- | --- |
| `cre_id` | string | yes | OpenCRE external id |
| `cre_name` | string | no | Display |
| `score_vector` | number | no | Cosine similarity |
| `score_rerank` | number | no | Cross-encoder score |
| `score_hybrid` | number | no | If BM25 hybrid used |

#### `ProposedLink`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cre_id` | string | yes | |
| `link_type` | string | yes | Align with OpenCRE `LinkTypes` when mapped (e.g. `Related`, `Supports`) |
| `confidence` | number | yes | Final score after rerank |
| `rationale` | string | no | Short explanation for logs |

#### `UpdateDetection`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `is_update` | boolean | yes | Same OWASP doc lineage |
| `prior_chunk_id` | string | no | Previous `chunk_id` for same artifact span |
| `prior_document_ref` | string | no | OpenCRE node id if already ingested |
| `adversarial_flags` | string[] | no | e.g. `CONTRADICTS_PRIOR`, `NEGATION_MISMATCH` |

Mapping to existing `cre_defs.Document` + `register_standard` is an implementation detail; `LinkProposal` is the pipeline contract.

## Handover out — human review (C → D)

### `ReviewItem`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | |
| `review_id` | string | yes | Unique review ticket |
| `chunk_id` | string | yes | From B |
| `artifact_id` | string | yes | From B |
| `pipeline_run_id` | string | yes | |
| `created_at` | string (date-time) | yes | |
| `status` | `review_required` | yes | |
| `reason_code` | string | yes | `BELOW_THRESHOLD`, `NO_CANDIDATES`, `ADVERSARIAL_FLAG`, `UPDATE_AMBIGUOUS` |
| `knowledge` | `KnowledgeSnapshot` | yes | |
| `retrieval` | `RetrievalAudit` | yes | Maintainer needs top candidates |
| `suggested_links` | `ProposedLink[]` | no | Best guess even if below threshold |
| `update_detection` | `UpdateDetection` | yes | |

## Logical API (future)

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/internal/oie/v0/librarian/classify` | `KnowledgeItem` → `LinkProposal` \| `ReviewItem` |
| `GET` | `/internal/oie/v0/librarian/review-queue` | Paginated `ReviewItem` for D |

## Example `ReviewItem`

```json
{
  "schema_version": "0.2.0",
  "review_id": "rev_20260201_00042",
  "chunk_id": "chk:art:OWASP/wstg:…:4",
  "artifact_id": "art:OWASP/wstg:document/4-Web_Application_Security_Testing/…",
  "pipeline_run_id": "20260201T020000Z",
  "created_at": "2026-02-01T02:40:00Z",
  "status": "review_required",
  "reason_code": "BELOW_THRESHOLD",
  "knowledge": {
    "text": "Do not use MD5 for password hashing.",
    "source": { "type": "github", "repo": "OWASP/wstg", "commit_sha": "def789", "committed_at": "2026-02-01T01:30:00Z" },
    "locator": { "kind": "repo_path", "id": "document/4-Web_Application_Security_Testing/…", "path": "document/4-Web_Application_Security_Testing/…" }
  },
  "retrieval": {
    "retriever": "pgvector+cross-encoder/0.1.0",
    "threshold": 0.8,
    "candidates": [{ "cre_id": "123-456", "cre_name": "Password storage", "score_vector": 0.72, "score_rerank": 0.76 }],
    "reranked": [{ "cre_id": "123-456", "score_rerank": 0.76 }]
  },
  "suggested_links": [{ "cre_id": "123-456", "link_type": "Related", "confidence": 0.76 }],
  "update_detection": { "is_update": false, "adversarial_flags": [] }
}
```

## Schema

- [schemas/link-proposal.json](./schemas/link-proposal.json)
- [schemas/review-item.json](./schemas/review-item.json)
