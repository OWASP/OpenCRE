# Module A stack — line-by-line review notes

**PRs:** [#1029](https://github.com/OWASP/OpenCRE/pull/1029) → [#1038](https://github.com/OWASP/OpenCRE/pull/1038) → [#1044](https://github.com/OWASP/OpenCRE/pull/1044)  
**Tip commit reviewed:** `week_8-chunking-retrieval` @ `6affe36`  
**Companion:** `blockers.md` (severity only). This file is file-level ask / keep / change.

---

## `application/utils/harvester/git_repository_client.py`

| Lines / area | Finding | Action |
|--------------|---------|--------|
| `checkout()` uses `git checkout -- <reference>` | `--` makes Git treat the argument as a **pathspec**, not a branch/commit. Checkout does not switch HEADs. | **Fix:** `["git", "-C", path, "checkout", reference]` after leading-dash reject. Add test that branch/commit switches. |
| `get_file_at_commit()` `git show f"{commit}:{path}"` | No `--end-of-options`. Path `--output=…` becomes a Git option (injection). | **Fix:** `git show --end-of-options f"{sha}:{path}"` or pass `--` and validate path. Reject leading `-` on path. Size-limit before loading huge blobs. |
| `clone` / `fetch` / `sync` | Solid atomic clone + lock pattern already on main. | **Keep.** |
| `get_file_at_commit` timeout=30 | Inconsistent with 300 elsewhere; OK for file read. | **Keep** (nit: document). |

---

## `application/utils/harvester/heading_extractor.py`

| Lines / area | Finding | Action |
|--------------|---------|--------|
| `stripped = line.lstrip()` then `startswith("#")` | Indented code and fenced blocks can look like headings. | **Fix:** track fence state; skip lines with ≥4 leading spaces; ignore `#` inside fences. |
| Range extend until same/higher level | Correct for ATX headings outside code. | **Keep** once fence/indent fixed. |
| No setext (`===` / `---`) support | Acceptable for OWASP md corpus. | **Out of scope.** |

---

## `application/utils/harvester/artifact_id.py`

| Finding | Action |
|---------|--------|
| `art:{repository}:{file_path}` matches contract mock shape | **Keep.** |
| Empty repo/path → `art:` or `art::` | Reject in validator (see below). |

---

## `application/utils/harvester/document_builder.py`

| Finding | Action |
|---------|--------|
| Builds from **full file text** at commit, not only added lines | **Keep** — correct for B. |
| `SourceInfo.repository` not `repo` | Rename at ChangeRecord emit (`source.repo`). |
| `SCHEMA_VERSION = "0.2.0"` | Align with contract pin; B does not version-gate. **Keep.** |
| `committed_at` as `datetime` on Document | Serialize ISO-8601 string for B. |

---

## `application/utils/harvester/document_validator.py`

| Finding | Action |
|---------|--------|
| `artifact_id.startswith("art:")` accepts `"art:"` | Require nonempty repo + path after prefix (split on `:`, ≥3 parts with nonempty). |
| No `locator.id` check | Require `locator.id` and `id == path` for `repo_path`. |
| Returns `bool` instead of raising | Prefer raise (like chunk validator) or keep bool but call from pipeline. |

---

## `application/utils/harvester/document_deduplicator.py`

| Finding | Action |
|---------|--------|
| NEW / UPDATED / UNCHANGED on content hash | **Keep** idea. |
| UNCHANGED: only flips status, skips commit/run metadata | **Fix:** always update `last_commit_sha`, `last_pipeline_run`, `last_processed_at`. |
| Registry is caller-injected | Wire to durable store or accept ephemeral only with DB checkpoint as source of truth. |

---

## `application/utils/harvester/artifact_registry.py` / `checkpoint_manager.py`

| Finding | Action |
|---------|--------|
| Pure in-memory `dict` | **Replace** checkpoint path with `CheckpointStore` → `harvester_checkpoint`. Artifact registry may stay in-process for a single run; must not be the only incremental memory. |
| `IncrementalPipeline` saves `last_processed_commit=""` | **Fix:** never persist empty SHA; write real SHA only after successful processing; use existing store. |

---

## `application/utils/harvester/incremental_pipeline.py`

| Finding | Action |
|---------|--------|
| Emits NEW/UPDATED only | **Keep.** |
| No document validation before emit | Call `DocumentValidator`. |
| No mismatch check: `document.source.repository` / `pipeline_run_id` vs args | Reject mismatched docs before checkpoint write. |
| Does not write `harvest_input` | Not this file’s job alone — need top-level runner. |

---

## `application/utils/harvester/chunker.py`

| Finding | Action |
|---------|--------|
| LlamaIndex `SemanticSplitterNodeParser` + HF embed | **Do not ship on prod `requirements.txt`.** Prefer `markdown_heading` / fixed-size from `repos.yaml`. Optional: keep semantic behind `requirements-dev` + env flag, off by default. |
| Empty text → `[]` | **Keep.** |
| Ignores `ChunkingConfig.max_tokens` / `overlap_tokens` / `strategy` | Honor YAML. |

---

## `application/utils/harvester/chunk_record_builder.py`

| Finding | Action |
|---------|--------|
| Builds span index/total/heading_path/offsets | **Keep** structure. |
| `IngestChunkRecord` omits `pipeline_run_id`, `source`, `locator` | **Fix:** emit full ChangeRecord-shaped payload (copy from Document). |
| `chunk_id` embeds heading + hash | Contract mock uses `chk:art:…:idx`. Either is fine if stable; prefer index-based `chk:{artifact_id}:{index}` for B fixture parity, or keep hash form but document. |
| Heading path from start line only | After heading-aware chunking, OK; with semantic cross-heading splits, wrong — fix chunker first. |

---

## `application/utils/harvester/chunk_record_validator.py`

| Finding | Action |
|---------|--------|
| Checks index/total/order | **Keep.** |
| Missing negative char offset reject | **Fix:** `start_char_idx >= 0`, `end_char_idx >= 0`. |
| Does not validate source/locator (because absent) | After B10 fix, validate or delegate to `ChangeRecord.model_validate`. |

---

## `application/utils/harvester/chunk_pipeline.py`

| Finding | Action |
|---------|--------|
| chunker → builder → validate each | **Keep** shape. |
| No provenance on records | Fixed in builder. |
| No DB write | Top-level `run_harvester` owns that. |

---

## `application/utils/harvester/models.py` (week 8 tip)

| Finding | Action |
|---------|--------|
| `Document` has provenance; `IngestChunkRecord` does not | Align chunk model with B `ChangeRecord` fields. |
| `SourceInfo.repository` | Emit as `repo` in JSON. |
| `DeduplicationStatus` / registry records | Fine as internal. |

---

## `requirements.txt` / `requirements-dev.txt`

| Finding | Action |
|---------|--------|
| Tip adds `llama-index-core`, `llama-index-embeddings-huggingface`, `textacy` to **prod** | **Revert from prod.** Dev-only if kept at all. Never pull sentence-transformers onto Heroku slug via HF embed path. |

---

## Tests

| Finding | Action |
|---------|--------|
| Broad unit coverage for builders/chunkers | **Keep** and extend. |
| Missing: ChangeRecord round-trip, `harvest_input` insert, CLI, git checkout switch, fence headings, oversized `git show` | **Add** in nits PR. |
| Diff pipeline benchmark env-gated | **Keep.** |

---

## What “done” looks like for Module A (acceptance)

```bash
python cre.py --run_harvester --run_id <R> --cache_file <db>
# exit 0, JSON summary on stdout
# harvest_input has pending rows for R whose payload passes ChangeRecord

python cre.py --run_noise_filter --run_id <R> --cache_file <db>
python cre.py --run_librarian --run_id <R> --cache_file <db>
```

Orchestrator sequences those three and waits on each exit code.
