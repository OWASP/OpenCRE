# Module D: The Reviewer

The fourth stage of the OIE pipeline: human-in-the-loop review over
`decision_queue`. Module C writes every decision there; the rows it could not
decide alone arrive as `status='review_required'` with a full RFC `ReviewItem`
envelope. This package consumes exactly those rows and nothing else.

```text
A (harvester) -> B (filter) -> C (librarian) -> decision_queue -> D (reviewer)
                                                     |
                                        linked rows -> graph writer (not D)
```

## The two rules

**`linked` rows are not D's.** They belong to the graph writer. Every read
(`DbReviewSource`) and every write-back (`mark_reviewed`) is filtered on
`status='review_required'`, so a human queue is structurally unable to retire an
auto-link, even handed the right id.

**The verdict is persisted before the row is retired.** `JsonlCorrectionsLog`
records the human's decision (fsync'd) first; `mark_reviewed` stamps
`consumed_at` second. A crash between the two leaves the row unconsumed and the
verdict re-recordable, never the reverse. This is the same rule Module C follows
against Module B's queue, one handoff downstream.

## What is in this package (D0)

| piece | file | what it does |
|---|---|---|
| Read side | `review_source.py` | `DbReviewSource` yields `PendingReview` rows, envelope validated back through the same pinned RFC model C emitted it with |
| Write-back | `queue_consumer.py` | `mark_reviewed` stamps `consumed_at`, idempotent, review rows only |
| Verdict log | `corrections_log.py` | append-only JSONL, one `ReviewVerdict` per line, the RFC's "no db bloat" decision |

A row whose envelope does not validate is skipped, logged by id, surfaced in
`unreadable_row_ids`, and **left unconsumed**. That is deliberately the opposite of C's
poison-row policy, because a decision row D cannot parse is C's audit record of
a decision, and retiring it would hide a C-side contract breach from the one
queue a human watches.

## The click-speed prototype

`docs/gsoc_2026_module_d/click_speed_prototype.html` is the founding RFC's
pre-code experiment: open it in a browser, review ten realistically shaped
items with `y`/`n`, and it measures whether the flow stays under the RFC's
3-second-per-item bar. The D1 UI is not allowed to be slower than this page.

## Not built yet

- **The review flow (D1).** Endpoints in the existing `/admin/` pattern wiring
  source -> human -> corrections log -> `mark_reviewed`.
- **The graph writer behind review (D2).** Approved rows go to a staging
  changeset (per `docs/designs/easier-importing.md`) and are applied through
  the same accept/apply pattern the imports admin API already uses. A human
  verdict is the safety evaluation that the W8 rule requires; the automated
  SafetyGuard detector (D3) comes last and lets high-confidence `linked` rows
  earn the right to skip the human.

## Contracts

- **C -> D:** [`docs/gsoc_2026_module_c/module_d_contract.md`](../../../docs/gsoc_2026_module_c/module_d_contract.md)
- The envelope model is imported from `application.utils.librarian.schemas`,
  so C and D cannot drift on what a `ReviewItem` is without one side failing loudly.

## Running the tests

```bash
python -m pytest application/tests/reviewer/ -q
```

Hermetic: in-memory SQLite, no API key, no model download.
