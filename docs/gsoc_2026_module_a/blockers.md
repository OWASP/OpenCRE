# Module A stack blockers (#1029 → #1038 → #1044)

**Audience:** maintainers finishing Module A after merging the GSoC week 6–8 stack.  
**Status:** open as of 2026-08-29 review.  
**Goal after fixes:** orchestrator can `run A → wait exit → B reads harvest_input → C`.

None of these PRs are merge-ready as an A *stage*. CI is green; the gaps are product/contract, not test failures.

---

## Shared (blocks e2e for all three)

| # | Blocker | Why it matters |
|---|---------|----------------|
| S1 | Nothing writes `harvest_input` | B has nowhere to read; A→B handoff missing |
| S2 | No `run_harvester` / `cre.py --run_harvester --run_id` | Orchestrator cannot start A or wait on exit |
| S3 | Chunk emit is not a Module B `ChangeRecord` | B validates with Pydantic and will mark rows `error` |

Until S1–S3 land, seed `harvest_input` manually (as draft orchestrator #996 already does).

---

## #1029 — week 6 (documents / artifacts)

| # | Blocker | Location |
|---|---------|----------|
| B1 | `git checkout -- <ref>` treats ref as **pathspec**, does not switch commits | `git_repository_client.py` `checkout()` |
| B2 | `git show {commit}:{path}` lacks `--` / `--end-of-options`; leading-dash paths are argv injection | `get_file_at_commit()` |
| B3 | Heading extractor treats indented / fenced `#` lines as headings | `heading_extractor.py` |
| B4 | Validator accepts `artifact_id="art:"`; never checks `locator.id` | `document_validator.py` |
| B5 | Internal `source.repository` vs contract `source.repo` | Must rename at persist boundary |

Week 6 is an acceptable *library* once B1–B4 are fixed. It is not an A stage alone.

---

## #1038 — week 7 (dedup / checkpoints)

| # | Blocker | Location |
|---|---------|----------|
| B6 | `ArtifactRegistry` and `CheckpointManager` are **in-memory dicts** | Die on process exit; ignore `CheckpointStore` / `harvester_checkpoint` already on `main` |
| B7 | `IncrementalPipeline` saves `last_processed_commit=""` then updates per doc | Crash mid-run leaves useless / dangerous checkpoint |
| B8 | UNCHANGED path does not refresh `last_commit_sha` / `last_pipeline_run` | Stale registry metadata |
| B9 | `DocumentValidator` never called from `process()` | Invalid docs can emit |

---

## #1044 — week 8 (chunking tip)

| # | Blocker | Location |
|---|---------|----------|
| B10 | `IngestChunkRecord` drops `pipeline_run_id`, `source`, `locator` | `chunk_record_builder.py` / `models.py` — B will reject |
| B11 | `llama-index-*` + `textacy` added to **prod** `requirements.txt` | Violates Heroku slug guard (torch / sentence-transformers off prod) |
| B12 | `repos.yaml` chunking config ignored | Config says `markdown_heading` + tokens; code always uses LlamaIndex semantic splitter |
| B13 | Semantic chunks can cross heading boundaries | Wrong `heading_path` for B’s LLM prompt |
| B14 | Negative `start_char_idx` not rejected | `chunk_record_validator.py` |

---

## Minimum finish checklist (post-merge “mod a nits”)

1. Fix B1–B4 (git argv + headings + validator).
2. Persist checkpoints via existing `CheckpointStore` / `harvester_checkpoint` (B6–B7).
3. Emit full `ChangeRecord`; validate with `application.utils.noise_filter.schemas.ChangeRecord` (B5, B10, B14).
4. Prefer `markdown_heading` / fixed-size chunking from `repos.yaml`; keep LlamaIndex **off** prod requirements (B11–B13).
5. Add `run_harvester(session, pipeline_run_id, …) -> RunSummary` and `cre.py --run_harvester --run_id`.
6. INSERT `harvest_input` rows: top-level `pipeline_run_id` == payload `pipeline_run_id`, `status=pending`.
7. Wire orchestrator to call A for real (not `todo` / skip-by-default).

---

## Out of scope for the nits PR (optional later)

- RSS / `feed_item` emission
- WSTG / SAMM / Top10 in `repos.yaml` (expand sources)
- Nightly GitHub Action (orchestrator or cron can own schedule)
- PDF / HTML extractors
