"""Module D — The Reviewer: human-in-the-loop review over ``decision_queue``.

The fourth stage of the OIE pipeline. Module C writes every decision to
``decision_queue``; the rows it could not decide alone carry
``status='review_required'`` and a full RFC ``ReviewItem`` envelope. This
package is the consumer of exactly those rows and nothing else.

Two rules, both inherited from the contract
(``docs/gsoc_2026_module_c/module_d_contract.md``):

- **``linked`` rows are not D's.** They belong to the graph writer. Every read
  and every write-back in this package is filtered on
  ``status='review_required'`` so a human queue can never retire an auto-link.
- **The verdict is persisted before the row is retired.** Stamping
  ``consumed_at`` tells the pipeline this chunk is finished; doing it before the
  human's verdict is durably recorded would destroy the one thing the review
  produced. Same rule Module C follows against Module B's queue.
"""
