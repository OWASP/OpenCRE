# How OIE mapping works

OpenCRE’s Integrated Ecosystem (OIE) turns published OWASP (and related)
standards into candidate links against the CRE graph. The system is a staged
pipeline: harvest text, drop obvious noise, retrieve candidate CREs, rerank
them, then either auto-link or send the chunk to human review.

Nothing in this article invents CRE edges for gold evaluation. Canonical gold
is a fixed answer key of CRE identifiers. Soft scoring may credit a prediction
that lands in the CRE’s graph neighborhood; that is a separate metric (see
[Evaluation and metrics](evaluation-and-metrics.md)).

## Pipeline overview

```text
Module A (harvester)
    → harvest_input
Module B (noise filter)
    → knowledge_queue
Module C (librarian)
    → LinkProposal  or  ReviewItem → Module D (human-in-the-loop)
```

| Module | Role |
|--------|------|
| **A** | Fetch repository revisions (often via GitHub tarballs or per-section URLs) and emit section-sized chunks. |
| **B** | Label chunks `KNOWLEDGE`, `UNCERTAIN`, or `NOISE`. Recall-first: uncertain text still reaches C. |
| **C** | Retrieve and decide. Never silently invents a link: every outcome carries a retrieval audit. |
| **D** | Human review for `review_required` envelopes (handoff table: `decision_queue`). |

Module C is hermetic by default: database access is confined to a factory
boundary so unit tests need no Postgres, API key, or downloaded model. Live runs
use pgvector CRE embeddings and a cross-encoder reranker.

## Librarian stages (Module C)

| Stage | Purpose |
|-------|---------|
| **C.0** | Validate a `knowledge_queue` row into an internal `Section` without rewriting body text. |
| **C.0.5** | Deterministic path: an explicit CRE id citation links without ML. |
| **C.0.4 / prior** | Optional problem-class / family prior; may cage the retrieval pool. |
| **C.1** | Dense retrieval over CRE embeddings → shortlist (typical *k* = 20). |
| **C.2** | Cross-encoder rerank of section↔CRE pairs (typical top-*k* = 5). |
| **C.3** | Temperature scaling toward calibrated probabilities (ECE gate in live eval). |
| **C.4** | Threshold τ and emit `LinkProposal` or `ReviewItem`. |

Supporting ideas that affect quality but are not separate numbered stages:

- **CRE summaries** — short librarian-only blurbs used as ranking text; they are
  not written to public `CRE.description` or Postgres embeddings.
- **Margin cutoff** — after rerank, keep the top score and any later score that
  clears a fraction γ of that top score (relative thresholding).
- **Prior cage / preferred-id inject** — graph and audit preferences that bias
  which CREs appear on the shortlist (defaults chosen for production-like eval).

## Theory behind the main design choices

### Dense retrieval (C.1)

Candidate CREs are found by embedding similarity in a vector index (pgvector in
live eval). This follows the dual-encoder / dense-passage retrieval pattern:
encode queries and documents into a shared space, then retrieve nearest
neighbors ([Karpukhin et al., Dense Passage Retrieval](https://arxiv.org/abs/2004.04906);
survey context in [Dense retrieval](https://en.wikipedia.org/wiki/Vector_database)
and [Semantic search](https://en.wikipedia.org/wiki/Semantic_search)).

OpenCRE stores one (or more) embedding rows per CRE. Hygiene of the embedded
string (titles, linked standard prose) matters more than exotic fusion when the
corpus is a few hundred CREs.

### Cross-encoder reranking (C.2)

A bi-encoder is fast but coarse. A cross-encoder scores the full
(section, CRE) pair and reorders the shortlist. The default model family is the
MS MARCO MiniLM cross-encoder line commonly used for passage reranking
([Nogueira & Cho on passage reranking](https://arxiv.org/abs/1901.04085);
[Sentence-Transformers cross-encoders](https://www.sbert.net/examples/applications/cross-encoder/README.html)).

Hybrid mixes of vector score, title overlap, and cross-encoder score appear in
learning-to-rank practice ([Learning to rank](https://en.wikipedia.org/wiki/Learning_to_rank)).
The promoted “Lawrence” mix uses β = 0 (no title boost) and γ = 0.70 on the
minmax-scaled cross-encoder term. That γ is **not** the margin γ below.

### Relative margin cutoff

When several CREs score close to the winner, emitting only rank-1 under-serves
multi-link sections; emitting the whole shortlist floods false positives. A
relative margin keeps rank 1 and every later item *i* with
`score_i ≥ γ · score_1` (promoted γ = 0.85). Relative thresholds of this form
are standard in retrieval and detection when absolute scores are poorly
calibrated ([Thresholding (decision theory)](https://en.wikipedia.org/wiki/Thresholding_(image_processing))
as analogy; ranking cutoffs in LTR systems).

### CRE summaries as ranking text

Cross-encoders need informative CRE-side text. Raw CRE names are short; public
descriptions may be missing or uneven. Cached LLM summaries built from name,
description, and linked standard prose improve C.2 without mutating the public
graph. Summaries stay off the REST/UI CRE page by design.

### Graph neighborhood (soft metric only)

The CRE graph uses typed edges such as **Related** and **Contains**. In OpenCRE
storage, PartOf is the reverse of Contains, not a separate edge type. Soft
evaluation credits a prediction if it matches gold **or** sits one hop away on
Related ∪ Contains. That measures “useful for gap analysis / RAG,” not
permission to expand gold when writing Links. Background on concept graphs:
[Knowledge graph](https://en.wikipedia.org/wiki/Knowledge_graph),
[Ontology (information science)](https://en.wikipedia.org/wiki/Ontology_(information_science)).

### Reciprocal Rank Fusion (experiment only)

When two retrieval pools are not score-calibrated, [Reciprocal Rank Fusion
(Cormack et al., SIGIR 2009)](https://dl.acm.org/doi/10.1145/1571941.1572114)
combines ranks with `1 / (k + rank)`. Dual-index + RRF was evaluated and **not**
promoted for the exact Links bar; see the
[experimental feature flags](https://github.com/OWASP/OpenCRE/tree/experimental-feature-flags)
branch.

## What “a link” means in production

An automatic link is a `LinkProposal` that cleared τ after calibrated scoring
and (eventually) a graph writer that refuses to commit behind an unevaluated
safety guard. Evaluation harnesses used for PR #1088 **do not write live Links**;
they score predicted CRE ids against gold fixtures.

## Related code

| Area | Path |
|------|------|
| Librarian package | `application/utils/librarian/` |
| Config / flags | `application/utils/librarian/config_loader.py` |
| B2 harness | `scripts/oie_owasp_eval/` |
| Promoted experiment YAML | `scripts/oie_owasp_eval/experiments/stack_winners.yaml` |
