# RAG/OIE Parity Feature Flags (staging)

All default **off** except `CRE_RAG_PARITY_QUEUE_ROW_LOCK` (default **on** — refuse silent degrade).

| Flag | Phase | Effect |
|---|---|---|
| `CRE_RAG_PARITY_INGEST` | 2 | Enable LI/Docling ingest path |
| `CRE_RAG_PARITY_DOCLING` | 2 | Prefer Docling loader |
| `CRE_RAG_PARITY_LI_HYBRID` | 3 | Hybrid/RRF retrieve adapter |
| `CRE_RAG_PARITY_LC_ROUTER` | 3 | LangChain router strangler (bypass regex) |
| `CRE_RAG_PARITY_CITATIONS` | 3 | Strip uncited sentences |
| `CRE_RAG_PARITY_MODERN_RERANK` | 4 | Cohere/modern rerank (needs measurement) |
| `CRE_RAG_PARITY_COMPRESSION` | 4 | Rerank-then-trim |
| `CRE_RAG_PARITY_CLAIMS` | 5 | knowledge_claim extract |
| `CRE_RAG_PARITY_LANGFUSE` | 6 | Langfuse callbacks (needs keys) |
| `CRE_RAG_PARITY_OTEL` | 6 | OTel export |
| `CRE_RAG_PARITY_REDIS_ANSWER_CACHE` | 7 | Shared Redis answer cache |
| `CRE_RAG_PARITY_QUEUE_ROW_LOCK` | 7 | Postgres SKIP LOCKED (default on) |
| `CRE_RAG_PARITY_LANGGRAPH_CHECKPOINT` | 7 | LangGraph Redis/Postgres checkpointer |

Decide policy is never flagged away — `opencre_decide_node` always calls OpenCRE `decide()`.
