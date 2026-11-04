# RAG/OIE Parity Feature Flags (staging)

Framework-native cutover is **wired** into ask (`comprehension/*`, `owasp_agent/router.py`) and optional Librarian C.1. Defaults stay **off** until measured (≥+3 pts, wrong-auto-link flat). `CRE_RAG_PARITY_QUEUE_ROW_LOCK` remains default **on**.

Ask-side keyword/FTS hybrid (`OWASP_CX_HYBRID` / `CRE_RAG_PARITY_LI_HYBRID`) was **removed** (2026-11-04): dense + LI QueryFusion / VectorStoreIndex only. Librarian `CRE_LIBRARIAN_HYBRID_*` (cross-encoder mix) is unrelated and unchanged.

## Canonical ask flags (`OWASP_CX_*`)

Prefer these for `scripts`/ablate — aliases below also work.

| Flag | Effect |
|---|---|
| `OWASP_CX_LI_RETRIEVE=1` | LI QueryFusion RRF over multi-query dense rankings (pgvector remains SoT) |
| `OWASP_CX_LI_VSTORE=1` | VectorStoreIndex over OpenCRE pgvector (read-only; no second SoT) |
| `OWASP_CX_LC_ROUTER=1` | Real LangChain tool-calling intent router (LiteLLM); fallback to regex if LC/LLM missing |
| `OWASP_CX_CITATIONS=1` | Strip uncited sentences after synthesize |
| `OWASP_CX_MODERN_RERANK=1` | Cohere/LI modern rerank via `phase4_rerank` (prefer over LLM `RERANK` when both close) |
| `OWASP_CX_RERANK=1` | Existing LLM passage rerank (unchanged) |

### Aliases (`CRE_RAG_PARITY_*` → same switches)

| Alias | Maps to |
|---|---|
| `CRE_RAG_PARITY_LI_RETRIEVE` | `LI_RETRIEVE` |
| `CRE_RAG_PARITY_LI_VSTORE` | `LI_VSTORE` |
| `CRE_RAG_PARITY_LC_ROUTER` | `LC_ROUTER` |
| `CRE_RAG_PARITY_CITATIONS` | `CITATIONS` |
| `CRE_RAG_PARITY_MODERN_RERANK` | `MODERN_RERANK` |

## Other parity flags

| Flag | Phase | Effect |
|---|---|---|
| `CRE_RAG_PARITY_INGEST` / `CRE_RAG_PARITY_DOCLING` | 2 | Docling/LI ingest → existing embeddings (`make rag-parity-ingest`) |
| `CRE_RAG_PARITY_COMPRESSION` | 4 | Rerank-then-trim |
| `CRE_RAG_PARITY_CLAIMS` | 5 | knowledge_claim extract |
| `CRE_RAG_PARITY_LANGFUSE` / `CRE_RAG_PARITY_OTEL` | 6 | Observability |
| `CRE_RAG_PARITY_REDIS_ANSWER_CACHE` | 7 | Shared Redis answer cache |
| `CRE_RAG_PARITY_QUEUE_ROW_LOCK` | 7 | Postgres SKIP LOCKED (**default on**) |
| `CRE_RAG_PARITY_LANGGRAPH_CHECKPOINT` | 7 | LangGraph checkpointer |

Decide policy is never flagged away — `opencre_decide_node` / Librarian always call OpenCRE `decide()`.

## Staging enable order (after Phase 1 corpus)

1. Finish CRE description approval → surgery → re-embed → `evaluate_librarian.py`
2. `OWASP_CX_LI_VSTORE=1` + `OWASP_CX_LI_RETRIEVE=1` (LI installed via requirements-dev)
3. `OWASP_CX_LC_ROUTER=1` (needs LiteLLM keys; latency gate — TASK-14.9)
4. `OWASP_CX_CITATIONS=1` (measure citation quality)
5. `OWASP_CX_MODERN_RERANK=1` only after ≥+3 pts vs baseline with wrong-auto-link flat (`COHERE_API_KEY` if using Cohere)

`LI_VSTORE` + `LI_RETRIEVE` + `CITATIONS` are in `DEFAULT_ON` (TASK-14.8 / 14.10); force off with `=0` for ablates. Rollback = git revert. Do **not** add LC/MODERN to `DEFAULT_ON` without ablation evidence.
