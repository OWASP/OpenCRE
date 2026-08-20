"""Module C — The Librarian.

Maps accepted knowledge chunks (from Module B) to OpenCRE nodes: either
auto-links them or routes them to human review.

Contracts (v0.2.0, RFC #734):
  B -> C : knowledge_queue row (the live handover; see
           docs/gsoc_2026_module_b/module_c_contract.md)
  B -> C : KnowledgeItem    (RFC envelope — the fixture/offline shape)
  internal: KnowledgeQueueItem (read-side mirror of B's SQL row)
  C -> graph : LinkProposal (confident auto-link, status=linked)
  C -> D : ReviewItem       (low-confidence / flagged, routed to HITL)

Scope so far:
  W1 (C.-1): contracts + config + eval harness + golden dataset.
  W2 (C.0):  input boundary — SectionValidator (validate/adapt without
             re-normalizing text) and ExplicitLinkResolver (fail-safe
             explicit-link resolution).
  W3 (C.1):  candidate retriever (in-memory + pgvector) + pipeline switch.
  W4 (C.2):  cross-encoder reranker — re-sorts the C.1 shortlist, fills reranked[].
  W5 (C.3):  confidence calibration — temperature scaling maps a rerank logit to
             an honest probability (fit by NLL on the golden set, gated ECE < 0.10).
  W6 (C.4):  decision engine — decide() turns a calibrated confidence into
             auto-link vs. review, with a reason code.
  W6b (C.4): envelope emitter + the C.0->C.4 LibrarianPipeline (dry-run).
  W7:        threshold sweep over the golden set; tau holds at 0.80. Analysis
             only, no code.
  W8:        live B->C integration — the queue mirror reconciled against B's
             merged table, a DB-backed source, the envelope sink, the
             consumed_at write-back, the component factory the orchestrator
             builds C from, and the safety seam wired into decide().

Not built yet: the SafetyGuard detector itself (the seam ships with
NullSafetyGuard, which evaluates nothing and says so), and the graph / review
writers — W8b. C still commits no links.

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
