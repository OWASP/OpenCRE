# Phase 1 CRE Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a one-shot CRE description generator (approval table under `tmp/`), hide `cre.description` in the frontend, and record the approved RAG/OIE parity design + this plan under tracked `docs/superpowers/`.

**Architecture:** Pure helpers live in `application/utils/cre_descriptions/` (not Librarian). The CLI `scripts/generate_cre_descriptions.py` loads CREs + linked embedding prose + neighbour names, calls LiteLLM via existing `metadata_enricher.default_metadata_llm_fn` / `prompt_client` patterns, and writes CSV/Markdown approval tables. No DB writes. Frontend omits description rendering only.

**Tech Stack:** Python 3, unittest, existing `embedding_quality`, LiteLLM via `litellm_router`, React/Jest for CRE page omit.

## Global Constraints

- Repo ignores `*.md` by default; track only via `.gitignore` exceptions for `docs/superpowers/specs/**/*.md` and `docs/superpowers/plans/**/*.md`.
- Do not port `cre_summary.py` as a product package; reuse `embedding_quality` / linked-ref loaders only.
- Do not write `cre.description` from the script; approval table only.
- Do not add LlamaIndex/LangChain/Langfuse/Ragas deps.
- Do not weaken Librarian `decide()` / τ.
- No staging/prod DB surgery or live full-corpus LLM in cloud CI.
- Hermetic tests must mock the LLM.

---

### Task 1: Gitignore + tracked docs

**Files:**
- Modify: `.gitignore`
- Create: `docs/superpowers/specs/2026-11-03-rag-oie-parity-design.md`
- Create: `docs/superpowers/plans/2026-11-03-phase-1-cre-descriptions.md` (this file)

- [ ] **Step 1: Add gitignore exceptions**

```gitignore
!docs/superpowers/specs/**/*.md
!docs/superpowers/plans/**/*.md
```

- [ ] **Step 2: Commit docs + gitignore**

```bash
git add .gitignore docs/superpowers/specs/2026-11-03-rag-oie-parity-design.md docs/superpowers/plans/2026-11-03-phase-1-cre-descriptions.md
git commit -m "docs: track RAG/OIE parity design and Phase 1 plan"
```

---

### Task 2: Junk filtering + grounding helpers (TDD)

**Files:**
- Create: `application/utils/cre_descriptions/__init__.py`
- Create: `application/utils/cre_descriptions/grounding.py`
- Test: `application/tests/cre_descriptions/grounding_test.py`

**Interfaces:**
- Produces: `usable_grounding_leaves(prose_list: Sequence[str]) -> List[str]`, `grounding_snippet(leaves: Sequence[str], neighbour_names: Sequence[str], max_chars: int = 400) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_usable_grounding_leaves_skips_nist_and_zap_junk(self):
    leaves = usable_grounding_leaves([NIST_CHROME, ZAP_JUNK, PCI_PROSE])
    self.assertEqual(len(leaves), 1)
    self.assertIn("Render PAN", leaves[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest application.tests.cre_descriptions.grounding_test -v`  
Expected: FAIL / ImportError

- [ ] **Step 3: Implement via `embedding_quality.usable_embedding_text` + `classify_content == "prose"`**

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add application/utils/cre_descriptions/ application/tests/cre_descriptions/grounding_test.py
git commit -m "feat: CRE description grounding filters junk prose"
```

---

### Task 3: Prompt builder + prompt_hash (TDD)

**Files:**
- Create: `application/utils/cre_descriptions/prompt.py`
- Test: `application/tests/cre_descriptions/prompt_test.py`

**Interfaces:**
- Produces: `build_description_prompt(cre_id, name, linked_prose, neighbour_names) -> Tuple[str, str]`, `parse_description_text(raw: str) -> str`, `compute_prompt_hash(system: str, user: str) -> str`

- [ ] **Step 1: Failing tests for name/id in user JSON, junk instructions in system, SHA-256 hash stable, JSON `{"description":...}` parse**

- [ ] **Step 2: Implement minimal prompt + parse + hash**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: CRE description prompt builder and hash"
```

---

### Task 4: Approval table emission (TDD)

**Files:**
- Create: `application/utils/cre_descriptions/table.py`
- Test: `application/tests/cre_descriptions/table_test.py`

**Interfaces:**
- Produces: `ApprovalRow` dataclass; `write_approval_csv(path, rows)`; `write_approval_markdown(path, rows)`  
- Columns: `cre_id`, `name`, `proposed_description`, `grounding_snippet`, `model`, `prompt_hash`

- [ ] **Step 1: Failing tests assert CSV header + MD table rows**

- [ ] **Step 2: Implement writers**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: CRE description approval table writers"
```

---

### Task 5: Generator orchestration + CLI (TDD)

**Files:**
- Create: `application/utils/cre_descriptions/generate.py`
- Create: `scripts/generate_cre_descriptions.py`
- Modify: `Makefile` (target `generate-cre-descriptions`)
- Test: `application/tests/cre_descriptions/generate_test.py`

**Interfaces:**
- Produces: `should_skip(existing_description: str, force: bool) -> bool`, `propose_descriptions(records, llm_fn, *, limit=None, force=False, model=..., dry_run=False) -> List[ApprovalRow]`
- CLI flags: `--cache-file`, `--limit N`, `--dry-run`, `--force`, `--output-dir` (default `tmp/`)

- [ ] **Step 1: Failing tests — skip non-empty description unless force; dry-run yields empty proposed_description and still emits rows; mocked LLM fills description**

- [ ] **Step 2: Implement generate helpers + script (local DB guard via `assert_local_db_url`; no DB UPDATE)**

- [ ] **Step 3: Makefile target**

```makefile
generate-cre-descriptions:
	@[ -d "./.venv" ] && . ./.venv/bin/activate || ([ -d "./venv" ] && . ./venv/bin/activate); \
	export PYTHONPATH="$(CURDIR)"; \
	python scripts/generate_cre_descriptions.py \
		--cache-file "$${CRE_CACHE_FILE:-postgresql://cre:password@127.0.0.1:5432/cre}" \
		$${LIMIT:+--limit $$LIMIT} $${FORCE:+--force} $${DRY_RUN:+--dry-run}
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: one-shot generate_cre_descriptions script"
```

---

### Task 6: Frontend hide `cre.description` (TDD)

**Files:**
- Modify: `application/frontend/src/pages/CommonRequirementEnumeration/CommonRequirementEnumeration.tsx`
- Create: `application/frontend/src/pages/CommonRequirementEnumeration/CommonRequirementEnumeration.test.tsx`

- [ ] **Step 1: Failing Jest test — CRE fixture with description must not render that text / `.cre-page__description`**

- [ ] **Step 2: Remove the description `<div>` from the CRE detail page**

- [ ] **Step 3: Run `yarn test -- CommonRequirementEnumeration` (or project jest config)

- [ ] **Step 4: Commit**

```bash
git commit -m "fix: hide CRE description on detail page"
```

---

### Task 7: Verification + PR

- [ ] **Step 1: Run checks**

```bash
make lint
make mypy   # if feasible
python -m unittest application.tests.cre_descriptions.grounding_test application.tests.cre_descriptions.prompt_test application.tests.cre_descriptions.table_test application.tests.cre_descriptions.generate_test -v
yarn test -- CommonRequirementEnumeration
```

- [ ] **Step 2: Push branch and open PR into `staging`**

PR body must list next human steps:

1. Run `make generate-cre-descriptions` (or limited) on homeserver with secrets
2. Approve `tmp/cre_description_approval.{csv,md}`
3. Staging surgery `UPDATE cre.description`
4. Re-embed CRE hub vectors
5. `python scripts/evaluate_librarian.py` (+ optional `score_b2_hop_distance.py`)

---

## Spec coverage self-check

| Spec requirement | Task |
|---|---|
| Gitignore exceptions | Task 1 |
| Design spec all phases | Task 1 |
| Phase 1 plan | Task 1 |
| One-shot script + Makefile | Task 5 |
| LiteLLM / prompt_client patterns | Task 5 |
| Grounding + junk filter | Task 2–3 |
| Approval table columns | Task 4 |
| `--limit` / `--dry-run` / skip / `--force` | Task 5 |
| Hermetic mocked LLM tests | Tasks 2–5 |
| Frontend hide description | Task 6 |
| No DB surgery / no new heavy deps | Global + Task 5 |
