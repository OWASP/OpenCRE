# RFC Workstream E — LLM rationale generation for cheat-sheet CRE links

**Status update:** this module was originally built as an LLM re-rank step
(Workstream D candidates in, ranked/explained shortlist out). Since then,
candidate retrieval *and* reranking for the whole mapping pipeline have
consolidated onto Module C ("The Librarian") — see PR #944's closing comment
and the merged PR #991. This doc describes the module as it stands now,
retargeted at a gap in Module C rather than duplicating its C.2 reranker.
Wiring it into `application/utils/librarian/emitter.py` is left to the
Module C maintainers to decide on; see the discussion on PR #1014.

The implementation is located in:

* `application/utils/external_project_parsers/parsers/cheatsheet_rerank.py`

## Dependency footprint

`langgraph` lives in `requirements-dev.txt`, not `requirements.txt` — it is
a dev/CI-only dependency, lazily imported inside `build_rationale_graph()`.
Importing this module, or calling `classify_confidence()`, never touches
`langgraph`. This matches the existing `sentence-transformers` entry in
`requirements-dev.txt` (Module C's own ML dependency, annotated "never
install on Heroku"), for the same reason: this module has no CLI/`cre.py`
wiring yet, so it must not grow the production web slug. Revisit this once
it's actually wired into a live import path.

## Sources for more context

* RFC: `docs/rfc/cheatsheets-llm-autonomous-mapping-rfc.md`
* Module C: `application/utils/librarian/` (`schemas.py`, `decision_engine.py`,
  `cross_encoder.py`, `emitter.py`)
* PR #944 (Workstream D, closed in favor of Module C):
  https://github.com/OWASP/OpenCRE/pull/944
* PR #991 (Module C week 6b — emitter + pipeline glue):
  https://github.com/OWASP/OpenCRE/pull/991

## The gap this fills

Module C's merged code has no code path that populates
`schemas.ProposedLink.rationale` — `emitter.py`'s `_proposed_links()` sets
`rationale=None` on every link, always. A cross-encoder (C.2) produces a
similarity score, not prose, so nothing downstream of it can fill that field
without an LLM. `decision_engine.decide()` also only ever surfaces a single
top-1 `cre_id` per chunk, so the scope of "explain the pick" is one
candidate, not a shortlist — this module is scoped accordingly.

## What it implements

`generate_link_rationale(section_text, cre_id, cre_text, score, ...) -> LinkRationale`
runs a small LangGraph flow:

```text
START -> generate --(success)--> format -> END
                  \--(failure)--> fallback -> format -> END
```

* **`generate`** — asks an LLM for one short, grounded sentence explaining
  why `cre_text` matches `section_text`, given Module C's calibrated
  `score`. Validated against a strict Pydantic schema (non-empty, capped
  length).
* **`fallback`** — runs on any LLM error, timeout (hard wall-clock cutoff,
  default 30s), or malformed/empty output. Produces a short, honest,
  score-only rationale ("Retrieval/rerank score 0.42; LLM explanation
  unavailable.") so a link is never blocked by an LLM hiccup.
* **`format`** — attaches confidence band (`classify_confidence`, RFC
  bootstrap thresholds 0.85/0.70, env-overridable) and an audit
  `RationaleTrace` (model, prompt version, UTC timestamp, fallback
  flag/reason).

The LLM call is dependency-injected (`llm_rationale_fn`), same seam pattern
as `embed_alignment.py`'s `ai_client` and `librarian/cross_encoder.py`'s
`score_fn`. Production defaults to a lazily-imported LiteLLM call; the full
test suite runs with a stub, no network/API key required.

## What this module deliberately does not do

* It does not retrieve or rerank candidates — Module C's C.1/C.2 own that.
* It does not decide auto-link vs. review — Module C's C.4 `decide()` owns
  that; `classify_confidence` here is a separate, human-facing utility only.
* It does not modify `application/utils/librarian/` — that's an actively
  developed, separately owned module. Wiring this in as the source of
  `ProposedLink.rationale` is proposed, not applied, pending discussion with
  the Module C maintainers.
