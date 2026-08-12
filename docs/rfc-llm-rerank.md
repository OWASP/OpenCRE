# RFC Workstream E — LLM Re-Rank and Decision Graph (LangGraph)

This document explains the implementation and behavior of RFC Workstream E
(LLM Re-Rank and Decision Graph) from the Cheatsheet to CRE Mapping RFC.

The goal of this module is to take the top-k CRE candidates retrieved for a
cheat sheet (Workstream D) and turn them into an explained, confidence-scored
shortlist that Workstream F can persist to `suggestions.json` for human
review.

The implementation is located in:

* `application/utils/external_project_parsers/parsers/cheatsheet_rerank.py`

## Acceptance criteria

- [ ] **Valid LLM result structure**: every `RankedCRE` returned has a
      non-empty `reason`, a `score` in `[0, 1]`, and a `confidence` of
      `"high"` / `"medium"` / `"low"` — verified by
      `test_successful_rerank_produces_reason_and_confidence`.
- [ ] **Deterministic fallback**: an LLM exception, timeout, malformed JSON,
      or an all-hallucinated response never raises out of
      `rerank_candidates_with_llm` — it always returns one `RankedCRE` per
      input candidate, each with `trace.fallback_used == True` — verified by
      `test_llm_exception_falls_back_to_retrieval_score`,
      `test_llm_timeout_falls_back`, `test_malformed_json_falls_back`, and
      `test_llm_returns_no_valid_candidates_falls_back`.
- [ ] **Auditable trace**: every result's `trace` carries `model`,
      `prompt_version`, an ISO-8601 UTC `generated_at`, and
      `fallback_used`/`fallback_reason` — verified by the same tests above.
- [ ] **Workstream F compatibility**: `RankedCRE.cre_id`, `.score`,
      `.confidence`, and `.reason` map 1:1 onto the RFC's
      `candidate_cres[]` entries in `suggestions.json` (section 4), so
      Workstream F can serialize a `RankedCRE` list directly.

---

## Sources for more context

* RFC: `docs/rfc/cheatsheets-llm-autonomous-mapping-rfc.md`
* Workstream B (structured extraction) doc: `docs/rfc-structured-extraction.md`

---

## What Workstream E implements

Given a `CheatsheetRecord` (Workstream B's contract,
`application/defs/cheatsheet_defs.py`) and a list of `CandidateCRE` (the
contract Workstream D's `retrieve_candidate_cres` is expected to return —
defined locally here since Workstream D has not landed yet), the module
exposes:

* `rerank_candidates_with_llm(record, candidates, ...) -> list[RankedCRE]` —
  the public entrypoint. Runs the LangGraph flow described below and always
  returns a usable, sorted, confidence-scored shortlist.
* `classify_confidence(score: float) -> str` — maps a 0-1 score to
  `"high"` / `"medium"` / `"low"` using the RFC's bootstrap thresholds
  (`>= 0.85` high, `>= 0.70` medium, else low), overridable via
  `CRE_CHEATSHEET_RERANK_HIGH_THRESHOLD` / `CRE_CHEATSHEET_RERANK_MEDIUM_THRESHOLD`.
* `build_rerank_graph()` — compiles and returns the raw LangGraph app, for
  direct inspection or integration testing.

### The LangGraph flow

```text
START -> rerank --(success)--> classify -> END
              \--(failure)--> fallback -> classify -> END
```

* **`rerank`** — builds a prompt from the cheat sheet's title/summary/headings
  and the candidate CREs, calls the injected `llm_score_fn`, and validates the
  response against a strict Pydantic schema (`_RerankPayload`, mirroring
  `application/prompt_client/embed_alignment.py`'s `AlignmentPayload`
  pattern). Any candidate `cre_id` the LLM invents that isn't in the original
  shortlist is dropped and logged, never trusted.
* **`fallback`** — runs whenever the LLM call raises, times out
  (`timeout_seconds`, default 30s, enforced with a hard wall-clock cutoff),
  returns malformed JSON, or scores zero valid candidates. It scores every
  candidate using its raw retrieval similarity instead, so the pipeline never
  crashes and never silently drops a cheat sheet.
* **`classify`** — assigns a confidence band and a `needs_review` flag
  (`true` when confidence is `"low"` or the run used the fallback path) to
  every candidate, attaches an audit `RerankTrace` (model name, prompt
  version, UTC timestamp, whether fallback was used and why), sorts
  descending by score, and truncates to `top_n` (default 5).

### Dependency injection / testability

The LLM call is injected as `llm_score_fn: (system, user, *, model) -> dict`,
the same seam pattern used elsewhere in this codebase (`ai_client` in
`embed_alignment.py`, `score_fn` in `application/utils/librarian/cross_encoder.py`).
Production code defaults to `default_llm_score_fn`, a thin LiteLLM wrapper
lazily imported so this module has no hard LLM dependency; tests inject a
deterministic stub, which keeps the graph — including both the success and
fallback paths — hermetically testable without any network or API key. See
`application/tests/cheatsheet_rerank_test.py`.

### What this module deliberately does not do

* It does not call Workstream D's retrieval — callers supply `CandidateCRE`s.
* It does not write `suggestions.json` — that's Workstream F
  (`build_suggestions` / `write_suggestions_json`), which is expected to
  consume `RankedCRE.reason` as the suggestion's `reason` field and
  `RankedCRE.confidence` as its `confidence` field.
* It does not decide auto-link vs. review on its own beyond the
  `needs_review` hint — Phase 1 is review-first for every suggestion
  regardless (RFC section 11), so `needs_review` is informational, not a
  gate.
