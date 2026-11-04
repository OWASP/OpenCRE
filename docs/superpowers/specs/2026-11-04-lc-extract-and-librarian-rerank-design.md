# LC extract + Librarian rerank offload (design)

**Status:** approved via chat (“do all the yes and the partials…”)  
**Date:** 2026-11-04

## Goal

Replace remaining hand regex/keyword mapping on the ask + Librarian workstream with LangChain structured extract and LI/modern-rerank paths, keeping fail-closed fallbacks.

## Decisions

1. **matched_slugs** — LC structured JSON extract over candidate slug/alias menu; phrase-match fallback.
2. **answer.py heuristics** — LC structured plan (`multipart`, `people_route`, `count_route`, …); regex fallback.
3. **Librarian C.2** — when `MODERN_RERANK` / parity modern rerank on, prefer phase4 rerank over title-boost hybrid mix; title_boost remains fallback.
4. **extras.keywords / phrase_queries / relaxed_and_queries / phrases** — delete (ask FTS gone).
5. **LC_ROUTER** — `DEFAULT_ON` with existing soft-gate + regex-first latency behavior; regex remains fallback.
6. **Science epic** — TASK-16 in cre-backlog (arXiv/blogs → measured experiments).

## Non-goals

- Frameworks owning `decide()` / τ
- Second embed SoT
- Staging enable of MODERN_RERANK without ≥+3pts ablate (flag wiring only)

## Verification

- Hermetic unittest for extract parsers + fallbacks
- Existing soft-gate / librarian / comprehension tests green
