# Module C → Module D contract — `decision_queue` v0.2

Module C writes rows to `decision_queue`; Module D reads them, acts on them, and
retires them. This file is the contract between the two.

It is the direct counterpart of
[`module_c_contract.md`](../gsoc_2026_module_b/module_c_contract.md), which
specifies B → C, and the handoff is deliberately the same shape: one table, the
producer inserts, the consumer sets `consumed_at`, nothing is ever deleted.

```text
A ──▶ harvest_input ──▶ B ──▶ knowledge_queue ──▶ C ──▶ decision_queue ──▶ D
```

## The table

`application.database.db.DecisionQueueItem`, created by migration
`e7c3b91d5a24_add_decision_queue`.

| column | null | who sets it | notes |
|---|---|---|---|
| `id` | no | C | primary key |
| `chunk_id` | no | A, via B and C | **A's identity — carried verbatim end to end** |
| `artifact_id` | no | A, via B and C | **A's identity — carried verbatim** |
| `pipeline_run_id` | no | A, via B and C | scopes one orchestrator pass |
| `schema_version` | no | C | the RFC envelope version (`0.2.0`) |
| `source_label` | yes | B, via C | B's `llm_label` on the chunk: `KNOWLEDGE` \| `UNCERTAIN` |
| `status` | no | C | `linked` \| `review_required` |
| `reason_code` | yes | C | review rows only; why it needs a human |
| `review_id` | yes | C | review rows only; the `ReviewItem` id |
| `confidence` | yes | C | calibrated top-1 confidence, when there is one |
| `envelope` | no | C | the whole RFC document (JSONB on Postgres, JSON elsewhere) |
| `created_at` | no | C | server default |
| `consumed_at` | **yes** | **D** | **the one column D writes** |

`created_at` / `consumed_at` are plain `DateTime`: the UTC wall clock is stored
and read back timezone-naive, matching `knowledge_queue`.

## Who does what

**C writes.** One row per decided chunk. Both outcomes go to the same table and
readers filter on `status` — exactly as B puts `KNOWLEDGE` and `UNCERTAIN` in one
queue.

| `status` | envelope in `envelope` | who consumes it |
|---|---|---|
| `linked` | `LinkProposal` | the graph writer |
| `review_required` | `ReviewItem` | Module D's HITL review |

Inserts are `ON CONFLICT (chunk_id, pipeline_run_id) DO NOTHING`. Replaying a run
is a no-op rather than a duplicate or an aborted batch. Uniqueness is per
*(chunk, run)*, not per chunk: B may legitimately re-offer the same chunk in a
later pipeline run, and that decision is its own record.

**D reads** `consumed_at IS NULL AND status = 'review_required'`, optionally
scoped by `pipeline_run_id`.

### `source_label`, and why it matters

Module B is recall-first: it drops `NOISE` and forwards both `KNOWLEDGE` and
`UNCERTAIN`. C reads both — an `UNCERTAIN` chunk is one B was unsure about
*classifying*, not one it judged worthless, and leaving it unread meant nothing
ever retrieved candidates for it.

B's uncertainty and C's confidence answer different questions: *is this security
knowledge* versus *which CRE does it match*. C does not currently treat the
first as a veto on the second, so an `UNCERTAIN` chunk whose calibrated
confidence clears τ will auto-link. `source_label` is what makes that visible —
a consumer that wants human sign-off on uncertain-sourced links can filter:

```sql
SELECT * FROM decision_queue
 WHERE status = 'linked' AND source_label = 'UNCERTAIN' AND consumed_at IS NULL;
```

If the team decides an `UNCERTAIN` chunk must never auto-link, that is a change
in C, not here — and it needs a fifth `reason_code` in the RFC, since the four
current ones all describe something other than "the source label was uncertain".

> **`linked` rows are not D's.** They are the graph writer's. A HITL queue that
> also surfaced auto-links would ask a human to re-approve decisions the pipeline
> already made with enough confidence not to.

**D writes** exactly one column, `consumed_at`, and never deletes a row — the
table is the audit trail of what C decided and what D did with it. Filter the
update on `consumed_at IS NULL` so a replay cannot move a timestamp that is
already set.

## The envelope

`envelope` holds the complete RFC document, validated against the vendored
schemas in `application/utils/librarian/_rfc_schemas/`. The columns beside it are
*projections* for filtering — they are read back off the same document and are
not a second source of truth.

Two things worth knowing before writing a validator against it:

1. **Absent optional fields are absent keys, not nulls.** The RFC types its
   optional fields as plain `"string"` and leaves them out of `required`, so
   `"repo": null` fails validation. C serialises with `exclude_none=True`. An rss
   envelope has no `repo`/`commit_sha`; a github one has no `feed_url`/`post_guid`.
2. **The retrieval audit travels with the decision.** `envelope.retrieval` carries
   the candidates, the reranked shortlist and the threshold, so a reviewer can see
   *why* a chunk landed where it did rather than being asked to trust a number.

## Reason codes

Review rows carry one, in this precedence order:

| `reason_code` | meaning |
|---|---|
| `NO_CANDIDATES` | retrieval returned nothing to link to |
| `ADVERSARIAL_FLAG` | the safety guard flagged the content |
| `UPDATE_AMBIGUOUS` | it restates an existing link, ambiguously |
| `BELOW_THRESHOLD` | the calibrated confidence did not clear τ |

`ADVERSARIAL_FLAG` and `UPDATE_AMBIGUOUS` cannot fire yet: the seam is wired into
`decide()`, but it ships with `NullSafetyGuard`, which evaluates nothing and
reports `evaluated=False`. Every real run today says so in its `RunSummary`
`status`. Treat a clean safety verdict as a default, not a finding.

## Versioning

`schema_version` is the RFC envelope version. Adding a nullable column or a new
`reason_code` is additive. Changing the meaning of `status`, or of an existing
reason code, is breaking — D filters on both.

## Related

- [B → C contract](../gsoc_2026_module_b/module_c_contract.md)
- [Module C package README](../../application/utils/librarian/README.md)
- [Runbook](runbook.md)
- [OIE RFC #734](https://github.com/OWASP/OpenCRE/pull/734)
