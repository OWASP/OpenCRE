"""Module C — The Librarian.

Maps accepted knowledge chunks (from Module B) to OpenCRE nodes: either
auto-links them or routes them to human review.

Contracts (v0.2.0, RFC #734):
  B -> C : KnowledgeItem    (RFC envelope — what B emits)
  internal: KnowledgeQueueItem (mirror of B's SQL row, master guide §1.2)
  C -> graph : LinkProposal (confident auto-link, status=linked)
  C -> D : ReviewItem       (low-confidence / flagged, routed to HITL)

Scope so far:
  W1 (C.-1): contracts + config + eval harness + golden dataset.
  W2 (C.0):  input boundary — SectionValidator (validate/adapt without
             re-normalizing text) and ExplicitLinkResolver (fail-safe
             explicit-link resolution). No retrieval/ranking logic yet.

Vendored RFC JSON schemas live under ``_rfc_schemas/``. They are pinned to
upstream/owasp-graph @ 2b1437987768d5ed20fe9ee721ab9a898c4b84af (PR #734).
Resync by running:

    git fetch upstream owasp-graph
    for f in link-proposal review-item knowledge-item proposed-link \\
             source-ref locator; do
        git show upstream/owasp-graph:docs/owasp-graph/apis/schemas/$f.json \\
            > application/utils/librarian/_rfc_schemas/$f.json
    done

Update the SHA above, then re-run the schemas test suite.
"""
