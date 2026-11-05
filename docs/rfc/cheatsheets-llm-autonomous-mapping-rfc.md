# RFC: Autonomous LLM Pipeline for OWASP Cheat Sheet to CRE Mapping

## Status
Draft

## Owner
OpenCRE contributors

## Goal
Refactor the current cheat sheet parser from backlink-only extraction into an autonomous, LLM-assisted pipeline that:

- discovers OWASP cheat sheets,
- optionally groups and categorizes them,
- proposes CRE mappings with evidence,
- and imports accepted results through the existing OpenCRE import flow.

This RFC intentionally scopes to cheat sheets first (not all OWASP resources) to validate quality, safety, and developer workflow quickly.

## 1. Context

Current `cheatsheets_parser` only maps when an explicit `opencre.org/cre/<id>` backlink exists in markdown.
That path is useful but incomplete.

PR #865 improves normalization and supplemental references. This RFC treats that contribution as a data sanity baseline and adds a second path: LLM-based suggestions.

## 2. Non-Goals (Phase 1)

- No automatic write to graph/database without review.
- No expansion to ASVS/Cornucopia/etc in this RFC.
- No requirement to build a perfect model; focus is deterministic workflow plus measurable quality.

## 3. Proposed Architecture

### 3.1 Pipeline Stages

1. Discover cheat sheet sources/files.
2. Extract structured entries from markdown (title, headings, key sections, URL).
3. Categorize/group entries (domain/topic clusters, optional).
4. Retrieve CRE candidates (embedding or lexical+embedding hybrid).
5. LLM re-rank and justify candidate links.
6. Emit import-ready suggestions (review-first artifacts) and pass approved results into normal import/register flow.

### 3.2 Output Modes

- `suggestions.json` (full candidate list with scores and rationale)
- `accepted.json` (human-approved subset)
- `ParseResult`/`Standard` entries generated from approved subset only

## 4. Suggestion Data Contract

Each suggestion item should look like:

```json
{
  "source": "owasp_cheatsheets",
  "cheatsheet_id": "Secrets_Management_Cheat_Sheet",
  "title": "Secrets Management Cheat Sheet",
  "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
  "category": "secrets-management",
  "candidate_cres": [
    {
      "cre_id": "623-550",
      "score": 0.86,
      "confidence": "high",
      "reason": "Discusses denial-of-service risk handling and operational controls."
    }
  ],
  "status": "suggested"
}
```

Approved suggestions become `defs.Standard` links using `defs.LinkTypes.AutomaticallyLinkedTo`, then flow through existing import registration paths.

## 5. Implementation Plan (Parallel Workstreams)

This split is designed for independent open-source contributors to work in parallel with clear ownership.

### Workstream A: Source Discovery and URL Normalization

**Deliverable:** `discover_cheatsheets()` and URL/file normalization module.

**Scope:**
- List cheat sheet markdown files from source repo.
- Normalize file references into canonical cheat sheet URLs.
- Validate against PR #865 supplement/normalization fixtures.

### Workstream B: Structured Extraction

**Deliverable:** `extract_cheatsheet_record(md_text)` and parser tests.

**Scope:**
- Extract title, major headings, concise summary text.
- Add fallback logic for non-standard markdown structure.
- Output a typed `CheatsheetRecord`.

**CheatsheetRecord contract (must implement):**

- `source` (`str`, required): fixed value `owasp_cheatsheets`.
- `source_id` (`str`, required): stable identifier derived from filename/path (for example `Secrets_Management_Cheat_Sheet`).
- `title` (`str`, required): human-readable cheat sheet title.
- `hyperlink` (`str`, required): canonical cheatsheetseries URL.
- `summary` (`str`, required): bounded summary text used downstream for retrieval.
- `headings` (`list[str]`, required): ordered heading list extracted from markdown.
- `raw_markdown_path` (`str`, required): original source path in repository.
- `category_hints` (`list[str]`, optional): lightweight labels inferred during extraction.
- `metadata` (`dict[str, str]`, optional): trace data such as parser version or extraction fallback reason.

**Contract rules:**

- Required string fields must be non-empty after normalization.
- `source_id` must be deterministic for the same input file.
- `headings` may be empty only when markdown has no headings.
- `summary` must be truncated to configured maximum length (documented constant).
- Contract validation errors should be explicit and include field name.

**Example record:**

```json
{
  "source": "owasp_cheatsheets",
  "source_id": "Secrets_Management_Cheat_Sheet",
  "title": "Secrets Management Cheat Sheet",
  "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
  "summary": "Guidance on secure storage, rotation, and operational handling of secrets.",
  "headings": ["Introduction", "Architectural Patterns", "Secret Rotation", "Operational Practices"],
  "raw_markdown_path": "cheatsheets/Secrets_Management_Cheat_Sheet.md",
  "category_hints": ["secrets-management", "operations"],
  "metadata": {
    "parser_version": "v1",
    "fallback_used": "false"
  }
}
```

### Workstream C: Categorization and Optional Grouping

**Deliverable:** `categorize_cheatsheet(record)` and `group_cheatsheets(records)`.

**Scope:**
- Add lightweight taxonomy labels (`auth`, `api`, `crypto`, etc.).
- Optionally assign cluster/group IDs for batch review.
- Provide deterministic fallback if LLM is unavailable.

### Workstream D: Candidate Retrieval

**Deliverable:** `retrieve_candidate_cres(record, top_k=20)`.

**Scope:**
- Query current CRE corpus.
- Implement baseline retrieval (existing embedding plumbing where possible).
- Return top-k CRE IDs with raw similarity.

### Workstream E: LLM Re-Rank and Decision Graph (LangGraph)

**Deliverable:** LangGraph flow for rank/filter/explain.

**Scope:**
- Input: `record + top-k candidates`.
- Output: scored shortlist with reason strings and confidence bands.
- Assign confidence levels: `high`, `medium`, `low`.
- Flag low confidence for manual review.

### Workstream F: Review Artifacts and Import Adapter

**Deliverable:** `suggestions -> approved -> ParseResult` adapter.

**Scope:**
- Write `suggestions.json`.
- Read reviewer-approved JSON and convert into `defs.Standard` with links.
- Integrate with normal import flow.
- Provide CLI/utility entrypoint for end-to-end execution.

## 6. Function-Level API (Initial)

```python
def discover_cheatsheet_sources(repo_url: str) -> list[str]: ...
def normalize_cheatsheet_url(path_or_url: str) -> str: ...

def extract_cheatsheet_record(markdown: str, source_path: str) -> CheatsheetRecord: ...
def categorize_cheatsheet(record: CheatsheetRecord) -> list[str]: ...
def group_cheatsheets(records: list[CheatsheetRecord]) -> list[CheatsheetGroup]: ...

def retrieve_candidate_cres(record: CheatsheetRecord, top_k: int = 20) -> list[CandidateCRE]: ...
def rerank_candidates_with_llm(record: CheatsheetRecord, candidates: list[CandidateCRE]) -> list[RankedCRE]: ...
def classify_confidence(score: float) -> str: ...

def build_suggestions(records: list[CheatsheetRecord]) -> list[MappingSuggestion]: ...
def write_suggestions_json(path: str, suggestions: list[MappingSuggestion]) -> None: ...
def load_approved_suggestions(path: str) -> list[MappingSuggestion]: ...

def suggestions_to_parse_result(approved: list[MappingSuggestion], cache: Node_collection) -> ParseResult: ...
```

## 7. LangGraph Flow

`Discover -> Extract -> Categorize -> Retrieve -> ReRank/Explain -> Threshold -> Persist Suggestions`

Guardrails:

- If retrieval fails: emit `status="needs_review"` and continue.
- If LLM call fails/timeouts: fallback to retrieval-only scoring.
- Always record trace metadata (`model`, prompt version, timestamp).

## 8. Validation and Quality Gates

### Baseline Sanity

- Use PR #865 normalized/supplement references as expected anchors.
- Ensure known existing mappings remain visible in candidate shortlist.

### Metrics (Phase 1)

- `Top-1` and `Top-5` hit rate on a small gold dataset.
- False positive rate after thresholding.
- Percentage of suggestions routed to human review.

### Test Plan

- Unit tests for each workstream function.
- Integration test for end-to-end suggestions generation.
- Golden sample fixture with around 20 cheat sheet records (seeded from PR #865 data).

## 9. Rollout Plan

N/A in this scenario, volunteer work, it gets rolled out as and when people have finished it.

## 10. Why Cheat Sheets First

- High-value but constrained input corpus.
- Fast iteration cycle for distributed contributors.
- Lets us harden evaluation and review workflow before scaling to ASVS, Cornucopia, and other OWASP assets.

## 11. Open Questions

- Should approved suggestions be applied immediately in parser runs, or only through explicit admin approval actions? Proposed default: explicit approval via CLI flow (for example, `--cheatsheets --import -y` for approved-only import). Without import approval flags, suggestions are shown for human review.

- What threshold defaults should be used initially for `high`, `medium`, and `low` confidence? Suggested bootstrap defaults: `high >= 0.85`, `medium >= 0.70 and < 0.85`, `low < 0.70`.
- Threshold defaults should definitely be recalibrated based on measured precision/recall from PR #865 normalization/supplement evaluation outputs.
- For Phase 1, rationale is persisted only in review artifacts (`suggestions.json` and `accepted.json`), not in durable core mapping metadata.

## 12. Contributor Delivery Pack: Issue Templates and Checklists

This section defines assignable issues (one per workstream), each with concrete acceptance criteria and a checkpoint-based implementation ladder.

### Issue A: Source Discovery and URL Normalization

**Goal:** Build reliable source discovery and canonical URL normalization for cheat sheets.

**Checklist items:**
- [ ] Implement `discover_cheatsheet_sources(repo_url)` that lists cheat sheet markdown sources.
- [ ] Implement `normalize_cheatsheet_url(path_or_url)` for canonical cheatsheetseries URLs.
- [ ] Add fixtures based on PR #865 reference/supplement data.
- [ ] Add unit tests for happy path and malformed paths.

**Acceptance criteria:**
- Discovery returns known cheat sheet filename in tests.
- Normalizer converts `cheatsheets/<Name>.md` to `https://cheatsheetseries.owasp.org/cheatsheets/<Name>.html`.
- Normalizer is idempotent (normalizing an already canonical URL returns the same URL).
- Tests cover at least 10 mixed inputs (valid file, valid URL, invalid path, edge case casing).
- No network dependency in unit tests.

**Implementation ladder with checkpoints:**
1. **Checkpoint A1 (Scaffold):** add module + function stubs + docstrings.
2. **Checkpoint A2 (Core logic):** implement deterministic file/path normalization.
3. **Checkpoint A3 (Fixture alignment):** add PR #865 based fixture cases.
4. **Checkpoint A4 (Tests):** complete unit tests and pass locally.
5. **Checkpoint A5 (Polish):** add short README snippet with examples.

### Issue B: Structured Extraction

**Goal:** Parse markdown into a typed `CheatsheetRecord`.

**Checklist items:**
- [ ] Define `CheatsheetRecord` structure (title, headings, summary, hyperlink, source id).
- [ ] Implement `extract_cheatsheet_record(markdown, source_path)`.
- [ ] Add fallback extraction rules when headings are missing.
- [ ] Add tests for at least 5 markdown formats.

**Acceptance criteria:**
- Extractor returns non-empty `title` for standard OWASP cheat sheet markdown.
- Extractor returns at least one heading when headings exist.
- For malformed markdown, extractor still returns a valid record with fallback title/source id.
- Summary length is bounded (for example 1-3 paragraphs or fixed token/char cap).
- Tests verify deterministic output on the same input.

**Implementation ladder with checkpoints:**
1. **Checkpoint B1 (Data model):** add `CheatsheetRecord` and validation helpers.
2. **Checkpoint B2 (Primary parser):** parse title/headings/body snippets.
3. **Checkpoint B3 (Fallback parser):** support missing title or irregular markdown.
4. **Checkpoint B4 (Tests):** cover normal, malformed, and minimal documents.
5. **Checkpoint B5 (Quality):** add extraction examples to docs.

### Issue C: Categorization and Optional Grouping

**Goal:** Label cheat sheets by domain and optionally group similar cheat sheets.

**Checklist items:**
- [ ] Implement `categorize_cheatsheet(record)` with controlled label set.
- [ ] Implement `group_cheatsheets(records)` returning stable group IDs.
- [ ] Provide deterministic fallback rules (keyword/rule based) when LLM is unavailable.
- [ ] Add tests for category consistency.

**Acceptance criteria:**
- Category labels come only from the existing approved taxonomy list in code.
- The same input record always returns the same category in deterministic mode.
- Group assignment is stable across repeated runs with same input ordering.
- Unknown/ambiguous inputs map to `uncategorized` (not errors).
- Tests cover at least 3 categories plus unknown case.

**Implementation ladder with checkpoints:**
1. **Checkpoint C1 (Taxonomy):** define taxonomy and label constraints.
2. **Checkpoint C2 (Rule baseline):** implement deterministic categorizer.
3. **Checkpoint C3 (Grouping):** add simple grouping strategy and stable IDs.
4. **Checkpoint C4 (Fallback):** integrate LLM-optional behavior with safe fallback.
5. **Checkpoint C5 (Tests):** add coverage for determinism and unknowns.

### Issue D: Candidate Retrieval

**Goal:** Retrieve top-k CRE candidates for each cheat sheet record.

**Checklist items:**
- [ ] Implement `retrieve_candidate_cres(record, top_k=20)`.
- [ ] Connect to existing CRE corpus retrieval plumbing.
- [ ] Return candidates with numeric similarity scores.
- [ ] Add benchmark script for small gold sample.

**Acceptance criteria:**
- Function returns exactly `top_k` results when enough CREs exist.
- Scores are sorted descending and normalized/consistent format.
- For gold dataset, known positive mapping appears in Top-5 for agreed baseline subset.
- Retrieval failures return `needs_review` path instead of hard crash.
- Tests include empty corpus and small corpus edge cases.

**Implementation ladder with checkpoints:**
1. **Checkpoint D1 (Interface):** define candidate object and retrieval contract.
2. **Checkpoint D2 (Baseline retrieval):** implement basic similarity retrieval.
3. **Checkpoint D3 (Sorting and scoring):** enforce stable top-k ordering.
4. **Checkpoint D4 (Resilience):** add graceful failure behavior.
5. **Checkpoint D5 (Benchmark):** run and record baseline Top-1/Top-5 on gold set.

### Issue E: LLM Re-Rank and LangGraph Decision Flow

**Goal:** Re-rank retrieved candidates using LLM pipeline and emit confidence decisions.

**Checklist items:**
- [ ] Build LangGraph flow for re-rank + explanation.
- [ ] Implement confidence classifier (`high`, `medium`, `low`) with thresholds.
- [ ] Add prompt/version metadata capture.
- [ ] Add fallback to retrieval-only scoring when LLM fails.

**Acceptance criteria:**
- Flow produces ranked output with rationale text for each accepted candidate.
- Confidence classification uses explicit threshold constants in code.
- Flow captures `model`, prompt revision identifier, and timestamp in output metadata.
- Timeout/API failure does not break run; fallback path is exercised in tests.
- At least one integration test covers end-to-end graph execution.

**Implementation ladder with checkpoints:**
1. **Checkpoint E1 (Graph skeleton):** create nodes/edges and typed inputs/outputs.
2. **Checkpoint E2 (Re-rank node):** implement prompt call and score parsing.
3. **Checkpoint E3 (Decision node):** add threshold-based confidence routing.
4. **Checkpoint E4 (Fallback node):** implement robust timeout/error fallback.
5. **Checkpoint E5 (Integration test):** validate full graph run with fixture data.

### Issue F: Review Artifacts and Import Adapter

**Goal:** Convert suggestions to review artifacts and approved suggestions into import-compatible `ParseResult`.

**Checklist items:**
- [ ] Implement `write_suggestions_json` and `load_approved_suggestions`.
- [ ] Implement `suggestions_to_parse_result(approved, cache)`.
- [ ] Add CLI entrypoint for full flow (`discover -> suggest -> review file -> import payload`).
- [ ] Add integration tests around artifact-to-import conversion.

**Acceptance criteria:**
- `suggestions.json` schema validates against RFC data contract.
- `accepted.json` entries convert into `defs.Standard` with `AutomaticallyLinkedTo` links.
- Unknown CRE IDs are reported clearly and skipped safely (no crash).
- CLI run exits non-zero on schema errors and zero on successful generation.
- End-to-end test demonstrates at least one approved mapping converted to `ParseResult`.

**Implementation ladder with checkpoints:**
1. **Checkpoint F1 (Schema + serializer):** define JSON schema and writer.
2. **Checkpoint F2 (Loader + validator):** load and validate approved suggestions.
3. **Checkpoint F3 (Adapter):** convert approved suggestions to import objects.
4. **Checkpoint F4 (CLI):** add simple CLI for generate/validate/convert.
5. **Checkpoint F5 (E2E test):** verify complete workflow with fixtures.

## 13. MVP Contribution Outcomes

This RFC is structured to support high-quality open-source delivery:

- Break large systems into clear function contracts and ownership boundaries.
- Build deterministic baselines before adding LLM complexity.
- Add tests and fixtures first, then iterate on behavior safely.
- Use acceptance criteria as definition of done, not just "code compiles."
- Measure quality (`Top-1`, `Top-5`, false positives) and improve systematically.

Even if Phase 1 aims for practical parity with PR #865-backed references through an LLM-enabled pipeline, a "good MVP" for this RFC is not perfect AI mapping. A good MVP is a reliable, testable, review-first pipeline that produces useful candidate mappings and integrates cleanly with OpenCRE's existing import flow.

