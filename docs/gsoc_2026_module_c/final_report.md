# Module C — The Librarian · GSoC 2026 final report

**Project:** OWASP Integrated Ecosystem (OIE) — a living knowledge graph of OWASP
security knowledge
**Module:** C, the Librarian — the decision stage
**Contributor:** Prateek Singh
**Organisation:** OWASP · OpenCRE

---

## What Module C does

OpenCRE links security requirements across standards. Keeping those links current
by hand does not scale: OWASP repositories change constantly, and every change is
a candidate link nobody has time to review.

The OIE pipeline automates the pass. Module A harvests changes, Module B filters
the noise, **Module C decides what each surviving chunk means**, and Module D puts
a human in front of what C could not decide alone.

```text
A (harvester) ──▶ harvest_input ──▶ B (noise filter) ──▶ knowledge_queue ──▶ C (librarian)
                                                                                  │
                                                                    ┌─────────────┴─────────────┐
                                                              LinkProposal                 ReviewItem
                                                            (auto-linked)               (human review) ──▶ D
```

C's whole job is deciding **when not to decide**. Auto-linking a wrong CRE
pollutes a graph other tools read as truth; sending everything to a human defeats
the automation. The value is in the boundary between those two.

---

## What was built

Seven stages, each a separately reviewed and merged pull request.

| Week | Stage | PR | What landed |
|---|---|---|---|
| 1 | C.-1 | [#922](https://github.com/OWASP/OpenCRE/pull/922) | RFC contracts, config, eval harness, 319-row golden dataset |
| 2 | C.0 | [#925](https://github.com/OWASP/OpenCRE/pull/925) | Input boundary — `SectionValidator`, `ExplicitLinkResolver` |
| 3 | C.1 | [#937](https://github.com/OWASP/OpenCRE/pull/937) | Candidate retriever (in-memory + pgvector) |
| 4 | C.2 | [#957](https://github.com/OWASP/OpenCRE/pull/957) | Cross-encoder reranker |
| 5 | C.3 | [#974](https://github.com/OWASP/OpenCRE/pull/974) | Confidence calibration — temperature scaling, ECE gate |
| 6 | C.4 | [#990](https://github.com/OWASP/OpenCRE/pull/990) | Decision engine — `decide()` |
| 6b | C.4 | [#991](https://github.com/OWASP/OpenCRE/pull/991) | Envelope emitter + C.0→C.4 pipeline glue |
| 7 | — | *analysis* | Auto-link threshold sweep; τ held at 0.80 |
| 8 | — | *this PR* | Live B→C integration — queue drain, sink, write-back |

**247 tests**, all hermetic — no database, API key, or model download required.

### Design decisions worth defending

**Seams, not implementations.** C.1 takes an `embed_fn`, C.2 a `score_fn`, C.3 a
scaler, C.4 a safety guard — each a `Protocol`. Live components and test stubs are
interchangeable, so decision logic is tested without ever loading a model. This is
why the suite runs in under four seconds.

**Nothing imports the database at module scope.** `factory.py` is the single
boundary where that stops being true, and even there the imports are
function-local. Hermetic testability was a constraint held for the whole project,
not an afterthought.

**Declared-degraded, never silently-degraded.** The recurring failure mode this
project kept finding — in its own code — is a check that skips and reports
success. It was caught three times:

1. The C.3 calibration gate returned 0 on a degenerate set, so a live run could
   exit green without the ECE gate ever running. Now returns non-zero.
2. `NullSafetyGuard` evaluates nothing, and *says so* — its verdict carries
   `evaluated=False`, counted and reported rather than looking clean.
3. When Module B's table shape moved, the eval harness rejected every row at the
   C.0 boundary — so the explicit gate had nothing to count, skipped itself, and
   the run still exited 0. Now a collapsed boundary fails the run explicitly.

Each was a case of a gate that looked green while measuring nothing.

**Consumption is gated on persistence.** Marking a queue row consumed tells
Module B never to offer that chunk again. Doing so while the envelope goes
nowhere destroys the chunk. The runner therefore refuses to retire anything
unless a sink reporting `persists=True` accepted the batch first.

---

## Results

Full numbers and methodology: [`final_metrics.md`](final_metrics.md).

| Stage | Result | Target | |
|---|---|---|---|
| C.0 boundary validation | 319/319 (100%) | — | |
| C.0.5 explicit resolver | 5/5 (100%) | 100% | ✅ |
| C.1 retrieval recall@20 | 285/292 (98%) | — | |
| C.2 rerank top-1 | 220/292 (75%) | ≥ 90% | ❌ |
| C.3 calibration ECE | 0.046 (T=1.105) | < 0.10 | ✅ |
| C.4 review recall | 5/5 (100%) | — | ✅ |
| C.4 auto-link recall | 176/314 (56%) | — | |

**The result I am most confident in is review recall: 5/5.** Every chunk that
should reach a human does. The engine never wrongly auto-links something that
needed review. For a component whose failure mode is polluting a shared graph,
that is the number that matters, and τ=0.80 buys it.

**The target I missed is top-1 accuracy: 75% against a planned 90%.** I want to be
precise about why, because the honest answer is more useful than the flattering
one.

Week 8's investigation tried thirteen reranker levers. All thirteen regressed —
C.2 as shipped scores net −7 against plain cosine similarity. The cause is not the
model: **427 of 428 CREs have empty `description` fields.** A cross-encoder scores
a (query, document) pair, and when the document side is effectively a bare title,
there is nothing to cross-attend to. C.1 still reaches 98% recall from embeddings
over that same thin corpus, which localises the problem precisely — the
information needed to *rank within* a shortlist mostly is not in the corpus.

Week 9's selective-reranking experiment reached 250/319 top-1 versus the shipped
238 by gating C.2 to fire only where it helps. It is deliberately unshipped: it
needs two calibrators and held-out validation there was not time to do honestly.
Shipping it on in-sample numbers would have been exactly the greenwashing this
project spent three separate fixes eliminating.

**The path to 90% runs through populating CRE descriptions, not through a better
reranker.** That is a corpus problem, upstream of Module C.

---

## Integration status

**B → C is live.** Module B writes `knowledge_queue`; C drains it, decides, and
stamps `consumed_at`. C's model matches B's table on all 23 columns.

C reads both of B's labels. B is recall-first — it drops `NOISE` and forwards
`KNOWLEDGE` and `UNCERTAIN` — so an `UNCERTAIN` chunk is one B was unsure about
*classifying*, not one it judged worthless. C originally skipped those, which
stranded them: nothing retrieved candidates for them, and with Module D
unimplemented they accumulated behind a `consumed_at` nobody would ever set. They
now run the full pipeline and are decided by the same rule as any other chunk:
clear τ and they link, fall short and they go to human review with candidates and
the audit attached. B's label records how sure B was and is preserved on every
decision row as `source_label`, so a consumer can weigh uncertain-sourced links
differently without C having to overrule its own calibrated confidence.

One qualification on that claim: it has been verified against SQLite through the
same SQLAlchemy models, not against a real Postgres. The types and the migration
are written for both, but the first Postgres run should be treated as a test.

This did not start out true. B's merged table ([#989]) was substantially richer
than the flat mirror C had been built against — `chunk_id`, `artifact_id`,
`content_hash`, the `locator_*` and span columns, RSS provenance. C failed on
100% of real rows and fabricated chunk ids it should have carried through
verbatim. Reconciling that is the bulk of Week 8, and the ids are now used as A
minted them.

**A → B is not yet connected.** Module A builds the harvester internals — repo
cloning, change detection, diff retrieval and parsing — but nothing writes
`harvest_input`, and A's `DiffBlock` is several transforms short of the
`ChangeRecord` shape B parses: chunking, id minting, run scoping. This is Module
A's remaining work, noted here because it means the end-to-end chain is not yet
demonstrable outside a fixture.

**C → D is built.** A real run writes one row per decided chunk to
`decision_queue` — the same shape of handoff B makes to C through
`knowledge_queue`: C inserts, D sets `consumed_at`, nothing is deleted. Both
outcomes share the table separated by `status`, the whole RFC envelope is stored
so a decision stays explainable, and inserts are idempotent per (chunk, run).
The contract is written down in [`module_d_contract.md`](module_d_contract.md).

Module D has no active implementation yet, so nothing reads those rows today —
but the table and its contract exist, so D has something concrete to build to.

---

## What is not built

Stated plainly, because a known gap is worth more than a vague claim.

- **The graph writer.** `decision_queue` carries the `linked` rows, but nothing
  yet reads them and commits an edge into the CRE graph. The rule that writer
  must honour is already written into `safety_guard.py`: it **must refuse to run
  behind a guard reporting `evaluated=False`**. Retiring a queue row without the
  safety path is recoverable — the decision is still in the table. Committing a
  wrong link into a graph other tools trust is not.
- **The SafetyGuard detector.** The seam is wired into `decide()`; the
  out-of-distribution scoring, conformal prediction, and update detection behind
  it are future work.
- **Selective reranking (W9).** Measured, promising, unvalidated. Do not ship
  without held-out data.

---

## Recommendations

1. **Populate CRE descriptions.** The single highest-leverage change available.
   It unblocks the top-1 target that no amount of reranker work reached.
2. **Do not lower τ below 0.80** without re-running the Week 7 sweep. The 100%
   review recall is bought with it.
3. **Re-fit `T` after any retriever, reranker, or corpus change.** It is a
   measured number, not a preference, and the live harness is the only place it
   is produced.
4. **Build W8b's writers behind the safety guard**, not beside it.
5. **Finish A → B** before claiming an end-to-end pipeline.

---

## Links

- [Package README](../../application/utils/librarian/README.md)
- [Runbook](runbook.md)
- [Final metrics](final_metrics.md)
- [B → C contract](../gsoc_2026_module_b/module_c_contract.md)
- [OIE RFC #734](https://github.com/OWASP/OpenCRE/pull/734)

[#989]: https://github.com/OWASP/OpenCRE/pull/989
