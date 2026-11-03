# OpenCRE RAG / OIE Parity Design

**Status:** approved  
**Date:** 2026-11-03  
**Scope:** Roadmap record for Phases 1–7. Phase 1 implementation is corpus work only.

## Product framing

OpenCRE is fail-closed standards mapping into a fixed CRE taxonomy — not a generic RAG app. Retrieval and generation must respect OpenCRE’s decide policy (`decide()` / τ). Frameworks may assist retrieval, synthesis, and observability; they must not own auto-link policy.

## Locked decisions

- **Env:** staging homeserver for runtime experiments; production GA remains cache-only.
- **Phase 1 storage B:** surgery writes `cre.description`; frontend does **not** render it. API may still return `description`.
- **Description generation is one-shot:** generate → human approval table → staging surgery. Re-run only when the CRE set grows. Not a forever Librarian runtime module.
- **`cre_summary.py` experiment:** steal ideas only (junk filtering, linked prose packing, LiteLLM patterns). Do **not** keep or port it as a product package for public descriptions.
- **New framework deps:** `requirements-dev.txt` only (later phases).
- **Frameworks (later):** LlamaIndex (hybrid / RRF / expand / filters / chunk / citation), LangChain (router + structured output), Docling, modern rerank, Langfuse + OTel, Ragas / DeepEval.
- **Decide:** LangGraph may orchestrate a decide **node** that **calls OpenCRE `decide()`**. Frameworks must NOT own auto-link policy. Low confidence → human.
- **Phase order:** 1 → 7; data before rerank.

## Parity matrix (abbrev)

| Use on staging (dev deps) | Keep in OpenCRE |
|---|---|
| LI / LC / Docling / Langfuse / Ragas | τ, Module D, CRE IDs, pgvector as SoT |
| Hybrid / RRF / multi-query / filters | Neighbourhood soft metric |
| Citation synthesizer, modern rerank | Hermetic CI without heavy deps |

### Promoted into phases

- **P2:** data holes + LI IngestionPipeline / Docling → our tables
- **P3:** LI hybrid / RRF / multi-query / metadata filters; LC router + schemas; citation synthesizer; flags then delete hand-rolled
- **P4:** modern rerank + contextual compression after descriptions exist; ≥+3 pts / wrong-auto-link flat
- **P5:** `knowledge_claim` + LC structured extract
- **P6:** Langfuse + OTel + LI/LC callbacks; Ragas / DeepEval bridged to gold
- **P7:** Redis answer cache; queue locking default-on; compression budgets; LangGraph checkpointer

### Do not take

- Mega-chain owning graph writes
- Framework confidence as auto-link
- Second `VectorStoreIndex` as source of truth
- Dify / Onyx for public chat
- `PropertyGraphIndex` / MS GraphRAG extractors

## Phase 1 detail (this PR’s code scope)

1. One-off script generates proposed CRE descriptions (LiteLLM / `prompt_client` patterns).
2. Approval table under `tmp/` (CSV and/or Markdown) for human review.
3. Staging surgery `UPDATE cre.description` — human / homeserver later (not this cloud job).
4. Frontend hides `cre.description` on CRE UI surfaces.
5. Re-embed + librarian eval — homeserver later.
6. Done — no runtime generator in the Librarian hot path.

### Phase 1 grounding rules

- Inputs: CRE name/id, linked Standard/Tool prose from embeddings when available, neighbour CRE names.
- Filter website chrome / ZAP junk / NIST banners; skip empty or junk-only sources.
- CLI: `--limit N`, `--dry-run`, idempotent skip when description already non-empty, `--force` to regenerate.
- Approval columns: `cre_id`, `name`, `proposed_description`, `grounding_snippet`, `model`, `prompt_hash`.
- Optional provenance DB columns are **not** required for Phase 1 MVP.

### Phase 1 non-goals

- No LlamaIndex / LangChain / Langfuse / Ragas deps yet.
- No staging Postgres surgery or live full-corpus LLM spend in cloud unless secrets clearly exist.
- No Module D, claims table, or hybrid retrieve.
- Do not weaken fail-closed Librarian `decide()` / τ.

## Later verification (homeserver)

```bash
make lint
make mypy
make test
# after approved surgery + re-embed:
python scripts/evaluate_librarian.py ...
python scripts/oie_owasp_eval/score_b2_hop_distance.py ...
# surgery with staging APP_NAME via scripts/db/
```

## Success criteria (Phase 1 PR)

- [x] Spec + Phase 1 plan committed and tracked (gitignore exceptions)
- [x] Generator script + Makefile target + hermetic tests
- [x] Frontend hides description
- [x] `make lint` + targeted tests green
- [x] PR open against `staging`
- [x] PR notes next human steps: run generator → approve table → staging surgery → re-embed → `scripts/evaluate_librarian.py`

## Implementation status (same PR #1200)

Phases 2–7 ship as `application/utils/rag_parity/` adapters + plans under
`docs/superpowers/plans/`, feature-flagged (`CRE_RAG_PARITY_*`), with hermetic
tests. Homeserver surgery / live LLM / full librarian eval remain human steps.
