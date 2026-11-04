# Still-to-port (TASK-14.8–14.17) — one commit per TASK

**Goal:** Land remaining LI/LC port tickets as separate commits on `ai-framework-migration`.

**Lane:** Watched local for code. Staging ablates / enablement for 14.9–14.11 ship gates → homeserver later (framework-port gate).

## Commit order

0. **HYBRID delete** (prerequisite, uncommitted) — remove ask-side keyword FTS
1. **14.8** — `LI_VSTORE` + `LI_RETRIEVE` in `DEFAULT_ON`
2. **14.14** — Dockerfile yarn EEXIST fix
3. **14.10** — CITATIONS cutover (DEFAULT_ON if low-risk strip; else wire + tests)
4. **14.11** — MODERN_RERANK path complete; keep default-off unless identity fallback safe
5. **14.12** — LI multi-query / metadata filters over vstore/retrieve
6. **14.13** — Trim dead hand-rolled dual path after 14.8
7. **14.9** — LC soft-gate latency (skip LLM when regex confident / cheap model)
8. **14.15–14.17** — Complete P5/P6/P7 adapters already sketched in `rag_parity/`

## Verification per commit

- Targeted unittest for touched area
- `black` on touched files
- Do not enable staging flags that need ablate without gate evidence
