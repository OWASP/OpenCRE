# Ingestion-time comprehension (design note, Phase 0)

Status: draft for review. Branch `feat/ingest-comprehension`, stacked on #1155.

## Problem
`ask` and the chatbot retrieve passages. Questions like "how many levels does SAMM have",
"which standards cover X and how do they differ" or "when was the last talk by an ASVS
maintainer" need knowledge that no single passage contains. #1155 patched four standards with
hand-written facts (`owasp_agent/node_facts.py`); that does not scale and was partly wrong
(SAMM has 3 maturity levels *per practice*, not 3 levels overall).

## What the corpus actually holds (staging DB, 2026-10-17)
| Standard | `node` rows | rows with a description |
|---|---|---|
| ASVS | 277 | 0 |
| OWASP AI Exchange | 64 | 0 |
| OWASP/masvs | 38 | 0 |
| SAMM | 30 (practices) | 0 |

Consequence: **structure is not stored in the CRE graph.** It exists only in harvested source
text (`repos.yaml` entries such as `owasp-samm`, markdown from the upstream repo, written to
`harvest_input` by Module A). Comprehension must therefore run over the *harvest output*
(whole documents), not over `node` descriptions, and write its results back to the node /
agent index with provenance.

## Approach
Gemini-class long context changes the economics: for most standards the **entire source fits
in one request**, so we do not need a chunk tree to get a holistic view.

1. **Whole-document digest (Gemini long context, strong model).** One pass per standard (or per
   repo path group) produces: overview, structure (levels, categories, counts, scope, edition),
   key terms. Every statement must cite source file + heading. Very large sources fall back to
   a RAPTOR-style two-level scheme (section summaries, then overview). RAPTOR (Sarthi et al.,
   ICLR 2024) = cluster + summarize recursively, retrieve across levels; GraphRAG (Edge et al.,
   2024) = LLM-built entity graph + community summaries, map-reduce at query time. We take the
   idea (precomputed multi-level summaries) not the machinery.
2. **Claim extraction (cheap Gemini Flash-class, bulk).** Per section: typed claims
   `{subject, predicate, object, quantity, scope, evidence:[{file, heading, quote_span}],
   confidence, extractor_version, source_hash}`. Verify pass (strong model) checks each quote
   actually supports the claim; failures are dropped or sent to Module D review.
3. **Graph-computed facts (no LLM).** Counts and lists over links come from SQL on the CRE
   graph, exposed as read-only tools to the synthesizer.
4. **People/events.** Same extractor over event pages / schedules / maintainer pages, linked
   to Nest leaders by project; "unknown" when no cited record. YouTube / chapter channels are
   a V2 issue.
5. **Query time.** Retrieve digests + claims + graph-tool results, one synthesis call that must
   cite claim ids; uncited sentences are stripped. Replaces `is_structure_ask` keyword gate.

## Storage (decision needed in Phase 1)
Option A: keep `document_metadata["facts"]` on nodes (cheap, but one standard = hundreds of
nodes). Option B (recommended): new `knowledge_claim` table keyed by `(subject_family,
source_hash)` plus embedded `digest` documents reusing the evidence-document channel in
`owasp_agent/meta_embeddings.py`. Claims invalidate when `source_hash` changes (reuse
`harvester/content_hash.py`).

## Testing: use each model for what it is good at
- **Gemini (long context):** reads a *whole* standard and generates the question set + reference
  answers with quotes (structure, comparison, counting, multi-standard), cheaply and at scale.
  Also produces the ground truth for held-out standards.
- **Claude:** independent judge of "is this answer entailed by the cited sources" and
  adversarial reviewer (finds questions where the system is confidently wrong). Different model
  family from the generator avoids self-agreement bias.
- **Cursor agents:** drive the existing probes against staging (`scripts/mcp_edge_probe_*`,
  small24, the 101 structure product-bads) and report pass-rate deltas; no new static asserts.
- Graph-truth for counts straight from SQL. Held-out standard ingested with no seeding.
- Calibrate judges once on ~30 human-checked Q&A. Track: grounded accuracy, citation
  precision, abstention on unanswerable, cost per document, p95 latency.

## Open questions
- Claim schema final shape and table vs metadata (Phase 1 spike on ASVS+SAMM+AIX).
- Which Gemini tiers via the shared LiteLLM router (`prompt_client/litellm_router.py`) and
  their per-doc cost at full-corpus scale.
- Backfill order and review-queue volume at the confidence threshold.
