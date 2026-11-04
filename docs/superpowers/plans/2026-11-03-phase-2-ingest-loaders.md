# Phase 2 — Data Holes + Ingest Loaders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** Fill Standard/Tool embedding prose holes via thin helpers and optional LlamaIndex IngestionPipeline / Docling loaders that write into **existing** harvest/embeddings tables (pgvector remains SoT).

**Architecture:** `application/utils/rag_parity/` adapters behind `CRE_RAG_PARITY_*` flags. Optional imports — hermetic CI runs without calling Docling/LI. No second `VectorStoreIndex` as SoT.

**Tech Stack:** Python, existing `embedding_quality`, optional `docling` / `llama_index` (requirements-dev).

## Global Constraints

- requirements-dev only for new framework deps
- Never weaken `decide()` / τ
- Hermetic tests mock LI/Docling
- Write into existing Embeddings / harvest tables only

---

### Task 1: Prose hole helpers + chunk quality

**Files:**
- Create: `application/utils/rag_parity/flags.py`
- Create: `application/utils/rag_parity/phase2_prose.py`
- Create: `application/utils/rag_parity/phase2_chunk_quality.py`
- Test: `application/tests/rag_parity/phase2_test.py`

---

### Task 2: Ingestion adapter (optional LI/Docling)

**Files:**
- Create: `application/utils/rag_parity/phase2_ingest.py`
- Create: `scripts/rag_parity_ingest.py`
- Modify: `Makefile` (`rag-parity-ingest`)

Writes via injected `EmbeddingWriter` protocol → existing DB upsert paths.
