# Phase 4 — Modern Rerank + Contextual Compression Plan

**Goal:** Env-gated Cohere (or identity fallback) rerank + rerank-then-trim compression.

**Flags:** `CRE_RAG_PARITY_MODERN_RERANK`, `CRE_RAG_PARITY_COMPRESSION` — default off.

**Ablation:** Enable on staging only after ≥+3 pts with wrong-auto-link flat (`ABLATION_NOTE` in `phase4_rerank.py`).
