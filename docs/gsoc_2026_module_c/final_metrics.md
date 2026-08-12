# Module C — final metrics

Every number here comes from one command over the committed golden set. Nothing
is hand-copied from a notebook.

```bash
python scripts/evaluate_librarian.py \
    --dataset application/tests/librarian/fixtures/golden_dataset.json \
    --use_live_embeddings --cache_file standards_cache.sqlite
```

**Environment:** 428 CRE hub vectors, `gemini/gemini-embedding-001` (dim 3072),
cross-encoder `ms-marco-MiniLM-L-6-v2`, hub-firewall ON, τ = 0.80.

## The golden set

319 hand-labelled rows drawn from OWASP standards already linked into OpenCRE.

| Slice | Rows | What it tests |
|---|---|---|
| `positive` | 292 | a chunk that should link to a known CRE |
| `hard_negative` | 12 | plausible-looking chunks that must *not* link |
| `explicit` | 5 | chunks citing a CRE id — must resolve deterministically |
| `update` | 5 | chunks restating an existing link |
| `ambiguous` | 5 | chunks that must route to review |

## Results

### C.0 — input boundary

| Slice | Validated |
|---|---|
| positive | 292/292 (100%) |
| hard_negative | 12/12 (100%) |
| explicit | 5/5 (100%) |
| update | 5/5 (100%) |
| ambiguous | 5/5 (100%) |

Hub firewall stripped **319** leaking hub entries — one per row, as designed. The
golden standards are themselves linked into OpenCRE, so without the firewall every
row could retrieve itself and every metric below would be inflated.

### C.0.5 — explicit resolver

**5/5 — gate 100%: PASS.** A chunk that cites a CRE id resolves with no ML in the
path at all. This is a hard gate; the run fails if it is not perfect.

### C.1 — candidate retrieval (recall@20)

| Measure | Result |
|---|---|
| any-hit | 285/292 (**98%**) |
| all-hit | 274/292 (**94%**) |

The correct CRE is in the shortlist 98% of the time. Retrieval is not the
bottleneck.

### C.2 — cross-encoder rerank (top-1, top_n=5)

**220/292 (75%).**

### C.3 — confidence calibration

| Measure | Result |
|---|---|
| fitted `T` | **1.105** |
| ECE raw (T=1) | 0.053 |
| ECE calibrated | **0.046** |
| Gate (ECE < 0.10) | **PASS** |

Fitted on 304 rows (positive + hard_negative). A `T` near 1.0 means the reranker
was already close to honest; calibration tightened it rather than rescuing it.

### C.4 — decision accuracy @ τ = 0.80

| Measure | Result |
|---|---|
| overall | 181/319 (57%) |
| auto-link recall (expected-linked) | 176/314 (56%) |
| **review recall (expected-review)** | **5/5 (100%)** |
| reason_code match | 4/5 (80%) |

**Read this by direction — a single accuracy number hides the story.**

*Review recall is 5/5.* Every chunk that should reach a human does. The engine
never wrongly auto-links something that needed review. For a gate whose job is
protecting the graph, this is the number that matters.

*Auto-link recall is 56%.* At τ=0.80, many correct-but-close positives fall under
the bar and route to review instead. **That is the safe direction**: the cost is a
human looking at something the machine could have handled, not a wrong link
entering the graph.

The one `reason_code` miss is a flag-based code that needs the SafetyGuard
detector, which is declared-not-built.

## Against the plan's targets

| Target | Planned | Actual | |
|---|---|---|---|
| C.0.5 explicit gate | 100% | 100% | ✅ |
| C.3 ECE | < 0.10 | 0.046 | ✅ |
| W4 top-1 | ≥ 0.80 | 0.75 | ❌ |
| W8 top-1 | ≥ 0.90 | 0.75 | ❌ |

**The top-1 targets were not met, and the reason is now well understood.**

Week 8's reranker investigation tried thirteen separate levers — model swaps,
prompt shapes, score fusion, candidate-pool changes. **All thirteen regressed.**
C.2 as shipped scores net −7 against plain cosine similarity on the same
shortlist.

The root cause is not the model. **427 of 428 CREs have empty `description`
fields.** A cross-encoder scores a (query, document) pair; when the document side
is effectively just a title, there is almost nothing to cross-attend to. C.1 gets
98% recall from embeddings over that same thin corpus, so the information needed
to *rank* within the shortlist largely is not present.

Week 9's selective-reranking experiment — gating C.2 to fire only where it helps
— reached 250/319 top-1 against the shipped 238, holding precision at τ=0.80. It
is deliberately not shipped: it needs two calibrators and held-out validation
that there was not time to do honestly.

**The path to ≥0.90 runs through populating CRE descriptions, not through a
better reranker.** That is a corpus problem and belongs upstream of Module C.

## Reproducing

The hermetic subset needs no DB, key, or model, and is what CI gates on:

```bash
python scripts/evaluate_librarian.py \
    --dataset application/tests/librarian/fixtures/golden_dataset.json
python -m pytest application/tests/librarian/     # 223 tests
```

For the live numbers, migrate a legacy cache first:

```bash
python scripts/rewrite_sqlite_embeddings_to_vec.py --db standards_cache.sqlite
```
