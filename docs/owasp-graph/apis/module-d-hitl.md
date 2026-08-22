# Module D — HITL & Logging

**Owner:** Fullstack  
**Consumes:** `ReviewItem` (Review Queue)  
**Produces:** `HumanDecision` → **corrections.jsonl** (and optional metrics export)

## Responsibility

Fast maintainer UI (approve / reject / correct link). Append-only correction log without DB bloat. Optional **loss warehousing** for retraining Module B/C.

## Handover in (C → D)

`ReviewItem` list; UI may also show `LinkProposal` history for the same `chunk_id` / `artifact_id` if user wants context.

## Handover out (D → feedback loop)

### `HumanDecision`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | |
| `decision_id` | string | yes | UUID |
| `review_id` | string | yes | From `ReviewItem` |
| `chunk_id` | string | yes | |
| `pipeline_run_id` | string | yes | |
| `decided_at` | string (date-time) | yes | |
| `decided_by` | string | yes | Maintainer id or handle |
| `action` | `approve` \| `reject` \| `correct` | yes | |
| `final_links` | `ProposedLink[]` | if approve/correct | Ground truth CRE links |
| `rejection` | `RejectionDetail` | if reject | |
| `loss_event` | `LossEvent` | no | Pro-mode training capture |
| `ui` | `UiMeta` | no | Timing for “3 second” experiment |

#### `LossEvent` (pro-mode)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `module` | `B` \| `C` | yes | Which stage was wrong |
| `input_snapshot` | object | yes | Copy of `KnowledgeItem` or `ReviewItem.knowledge` |
| `wrong_prediction` | object | yes | e.g. suggested links or `is_security_knowledge` |
| `correct_label` | object | yes | Maintainer ground truth |
| `notes` | string | no | Free text |

#### `UiMeta`

| Field | Type | Required |
| --- | --- | --- |
| `review_duration_ms` | integer | no |
| `keybind_used` | string | no | e.g. `y`, `n` |

## Logical API (future)

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/internal/oie/v0/review/items` | Next `ReviewItem` for UI |
| `POST` | `/internal/oie/v0/review/items/{review_id}/decisions` | Submit `HumanDecision` |

MVP: UI reads review JSONL from blob store; appends one line per decision to `corrections.jsonl`.

## Downstream use of corrections

| Consumer | Use |
| --- | --- |
| Golden dataset CI | Add rows to `golden_dataset.json` for B/C regression |
| Module C retrain | `loss_event` pairs for reranker fine-tuning (future) |
| OpenCRE ingest | On `approve`/`correct`, emit or update `Document` links |

## Example `HumanDecision` (correct)

```json
{
  "schema_version": "0.2.0",
  "decision_id": "550e8400-e29b-41d4-a716-446655440000",
  "review_id": "rev_20260201_00042",
  "chunk_id": "chk:art:OWASP/wstg:…:4",
  "pipeline_run_id": "20260201T020000Z",
  "decided_at": "2026-02-01T10:05:00Z",
  "decided_by": "maintainer@owasp.org",
  "action": "correct",
  "final_links": [
    { "cre_id": "123-456", "link_type": "Related", "confidence": 1.0, "rationale": "Human verified" }
  ],
  "loss_event": {
    "module": "C",
    "input_snapshot": { "text": "Do not use MD5 for password hashing." },
    "wrong_prediction": { "suggested_links": [{ "cre_id": "123-456", "confidence": 0.76 }] },
    "correct_label": { "cre_id": "123-456", "link_type": "Related" }
  },
  "ui": { "review_duration_ms": 2100, "keybind_used": "y" }
}
```

## Schema

- [schemas/human-decision.json](./schemas/human-decision.json)
