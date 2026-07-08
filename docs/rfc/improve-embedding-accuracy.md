# RFC: Improve embedding accuracy via agent-aligned excerpts and `embeddings_url`

**Status:** Draft / Proposed  
**Scope:** Node (standard/tool) embedding generation; relationship between importer `hyperlink` and stored embedding metadata  
**Related code:** `application/prompt_client/prompt_client.py` (`in_memory_embeddings`), `application/database/db.py` (`Embeddings.embeddings_url`)

## 1. Summary

Today, when we fetch a remote page to embed a standard node, we use essentially the **entire document body** (HTML via Playwright `body.inner_text()`, or full PDF text). That dilutes the vector with navigation, footers, unrelated sections, and other controls that may live on the same URL.

This RFC proposes an **optional pipeline** after download:

1. An **agent** (LLM with structured output) interprets the page together with the node’s **section / subsection / section_id** (and related fields).
2. If a **specific region** of the page best matches that standard slice, we **embed only that region’s text**.
3. When that region is best addressed by a **URL fragment** (`#id`) that exists on the page, we persist the resolved URL in **`embeddings_url`** (not by overwriting **`hyperlink`**).

**Product language:** `hyperlink` stays the spreadsheet / import source of truth; **`embeddings_url`** holds the narrower, embedding- and fetch-oriented URL after import. **The database is the source of truth for runtime behavior**; we do not rewrite import artifacts.

OpenCRE is **English-only** for this work: prompts, heuristics, and fixtures assume English content.

## 2. Motivation (why)

- **Signal vs noise:** Full-page embeddings hurt retrieval when one URL hosts many controls or long narrative text.
- **Alignment with the catalog:** We already model **section / subsection**; embeddings should reflect **that row**, not the whole page chrome.
- **Inspectable deep links:** A resolved `embeddings_url` with a validated fragment makes it clear **which span** was embedded and supports manual QA in the browser.
- **Visual guide for users:** When the UI or docs surface **`embeddings_url`**, the user should land on the **document section** that actually corresponds to their standard (e.g. “Indirect prompt injection”), not merely the first place those words appear (e.g. an opening overview that lists several topics including mitigations). Same-page deep links should **scroll the viewport to the right heading block**, not to a generic intro paragraph.
- **Separation of concerns:** Importers and spreadsheets keep stable **`hyperlink`** values; the system may **refine** only what we use for fetch/embed, via **`embeddings_url`**.

## 3. Current behavior (baseline)

- Valid `http(s)` **`hyperlink`** on the node → Playwright `goto` → `body.inner_text()` → normalize/clean → embed; optional `metadata` merged in; fallback to serialized node fields if remote text is missing or empty.
- No LLM step; no DOM region selection; no automatic refinement of URLs for embedding.
- The `Embeddings` row can store **`embeddings_url`** (today often aligned with the node link when adding embeddings); this RFC **extends** that field’s role as the canonical “what we fetched / aligned to” URL.

## 4. Goals and non-goals

### Goals

- Improve embedding quality on **noisy or multi-topic** pages.
- When confidence and DOM checks pass, set **`embeddings_url`** to a **narrower** URL (e.g. same page + validated `#fragment`).
- Keep **`hyperlink`** unchanged post-import (spreadsheet source of truth).
- **Deterministic enough** for operations: logging, metrics, feature flags, rollback.

### Non-goals (initial v1)

- Changing **import CSV/sheets** or other **import artifacts** on disk.
- i18n: **English only**.
- Guaranteed perfect alignment on every site (especially SPAs with weak or missing fragment semantics).
- Replacing the entire retrieval stack with a separate document platform (e.g. not required to adopt LlamaIndex for v1).

## 5. Proposal (what we are building)

### 5.1 Feature flag

- **`CRE_EMBED_SMART_EXTRACT=off|on|shadow`** (default in code: **`on`** unless set to `off` or `shadow`)
  - **`off`:** Current behavior (full body / full PDF text).
  - **`on`:** Excerpt embedding + optional **`embeddings_url`** update when thresholds pass.
  - **`shadow`:** Compute excerpt + candidate `embeddings_url` for logging/metrics; keep production embedding input unchanged until validated.

### 5.2 Pipeline (high level)

1. **Fetch** (existing): Playwright for HTML; PDF path unchanged where applicable.
2. **Parse and segment (HTML):** Build a **linear, element-bounded** representation (blocks with stable ids: tag, `id`/`name` if present, text, and a machine pointer such as xpath or CSS path for internal use only—not exposed as API).
3. **Optional boilerplate removal:** Run **Readability**-style or **trafilatura** extraction to shrink candidates before segmentation (configurable).
4. **Agent / scorer (LLM):**
   - **Inputs:** Node labels (`name`, `section`, `subsection`, `section_id`, description if present) + candidate blocks (and optional TOC if detectable). Instructions must encode §5.3: target the **author-intended section** for this standard, not the first co-mention in an overview.
   - **Output (strict JSON):** chosen span (block id range or equivalent), `confidence`, optional `suggested_fragment`, `should_fallback_full_page`, short `rationale` for audit logs.
5. **Embed:** Concatenate text from the chosen span only; same embedding model and provider integration as today.
6. **`embeddings_url` update (conditional):**
   - If `suggested_fragment` matches an existing element `id`/`name` on the page, confidence ≥ threshold, and policy allows → set **`embeddings_url`** to `canonical_base + fragment` (or equivalent normalized form).
   - **`hyperlink`:** never updated by this pipeline.
   - If no valid fragment or confidence is low → **`embeddings_url`** may still reflect “same URL, excerpt only” semantics via stored excerpt metadata (see §6.3), or remain unchanged per policy.

### 5.3 Document sections vs incidental mentions (UX requirement)

Alignment must prefer the **structural section** of the page that is *about* the catalogued standard, not the **first span** that lexically mentions related terms.

**Example:** A single long page is broadly about **prompt injection**. A node describes **indirect prompt injection**. The page may open with a paragraph that mentions “indirect prompt injection” alongside other themes (e.g. mitigations, taxonomy, or links to other sections). The pipeline must still select the **subsection whose heading and body constitute the indirect-prompt-injection control** (and set **`embeddings_url`** to that section’s anchor when one exists), so that when a user opens the link they see the **right block of content** in view—not only a better embedding, but a **clear visual guide** to what OpenCRE is mapping.

**Implications for the agent and heuristics:**

- Prefer blocks under a **heading** whose title matches the standard slice over **introductory** or **TOC-style** paragraphs that merely name the topic.
- Treat **early mentions** that also reference unrelated siblings (e.g. “Mitigations” for the whole page) as **lower priority** than the dedicated section for the row’s `section` / `section_key`.
- Prompting and evaluation fixtures should include **multi-section single-URL** pages so we regress “wrong first-hit” behavior.

### 5.4 Safety rules

- Do not set a fragment that **does not exist** on the fetched DOM.
- On ties or ambiguity, **prefer full-page excerpt policy or no URL change** over a wrong `#`.
- **Idempotency:** `embeddings_content` hashing must include **excerpt boundaries + policy version + normalized `embeddings_url`** so we do not thrash on small unrelated DOM changes (tune sensitivity explicitly).

## 6. Detailed design (how)

### 6.1 English-only

All prompts, block labels, and evaluation datasets are **English**. No multilingual routing in v1.

### 6.2 “Anchor” semantics

- Prefer real **`id="..."`** attributes on headings/sections in static HTML. In the URL, the same target is the **fragment** **`#...`**: e.g. element `id="indirect-prompt-injection"` → append **`#indirect-prompt-injection`** to the base URL (the **`#` is URL syntax**; the fragment value must match the element’s `id` or a validated `name` where applicable).
- Stable **`name="..."`** on anchors can also define targets; the corresponding URL fragment uses **`#`** plus that name when the browser resolves it for same-document navigation.
- Do not **invent** fragments for client-only scroll behavior without a real `id`/`name` in the document.
- **PDF:** excerpt by page/paragraph when useful; fragment-style **`embeddings_url`** updates are usually **not** applicable unless the deployment uses PDF destinations—default is **no fragment rewrite** for PDF.

### 6.3 Where state lives (resolved)

| Field | Role |
|--------|------|
| **`node.link` (`hyperlink` in defs)** | **Unchanged** after import; **spreadsheet / importer source of truth**. |
| **`Embeddings.embeddings_url`** | **May be updated** to the narrower, validated URL used for fetch/embed alignment (e.g. with `#section`). |
| **`Embeddings.embeddings_content`** | Text (or normalized text) actually embedded; should correspond to the chosen span. |

Optional later: JSON on the embeddings row for **`embeddings_source_span`** (block ids, byte offsets) and **`embeddings_excerpt_policy_version`** for clearer audit trails without overloading `embeddings_content`.

### 6.4 Import artifacts (resolved)

- **We do not touch import artifacts.** After import, **the database** is the source of truth for **`embeddings_url`** and embedding payloads.

## 7. Caching: same URL, different subsections (resolved)

Many nodes can share the **`hyperlink`** (same normalized URL) while referring to **different** subsections. Caching must reflect that.

**Two layers:**

1. **Page / parse cache — keyed by normalized URL**  
   One fetch and one DOM→block-list (or PDF text) parse per URL per job (or TTL). Avoids repeated Playwright hits and repeated parsing for many CRE rows pointing at the same page.

2. **Alignment cache — keyed by `(normalized_url, section_key)`**  
   `section_key` is a stable derivative of fields that distinguish rows on the same page, e.g. hash or tuple of **`(section, subsection, section_id)`** (normalized).  
   - **Same URL + same `section_key`:** reuse one LLM alignment / excerpt result (e.g. duplicate rows or re-runs).  
   - **Same URL + different `section_key`:** **different** excerpt and possibly **different** `embeddings_url` fragment — each gets its own alignment call; only the **heavy** download/parse is shared.

So: **content is cached per URL; alignment is cached per (URL, section_key).** Different subsections on the same page are first-class.

## 8. Technology choices

| Layer | Recommendation | Notes |
|--------|----------------|--------|
| Fetch | **Playwright** (existing) | Needed for JS-heavy pages. |
| HTML cleanup | **`trafilatura`** or **readability-lxml** | Optional; reduces noise before segmentation. |
| Segmentation | **Custom** (BeautifulSoup / lxml) | Stable block ids for the LLM; full control. |
| Optional pre-rank | **rank_bm25** or simple TF-IDF | Reduces tokens sent to the LLM. |
| Agent | **Vertex AI or OpenAI** (existing integrations) | Structured JSON output; reuse project `ai_client` patterns. |
| **LlamaIndex** | **Not required for v1** | Useful for large multi-document corpora and query engines; this problem is **one URL + a known section label**—a **short custom pipeline** is simpler to test and ship. Revisit if we unify many sources into a single RAG index later. |
| PDF | **pypdf** (existing) | Same as today; excerpt by span where applicable. |

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Wrong excerpt → bad retrieval | `shadow` mode; confidence thresholds; golden URL fixtures; sampling. |
| LLM cost / latency | BM25 pre-filter; page cache; alignment cache per `(url, section_key)`. |
| DOM drift | Policy version; fallback to full-page behavior when validation fails. |
| SPAs / weak ids | Skip fragment update; excerpt-only or full-page per policy. |

## 10. Success metrics

- Offline: human or model-graded “does retrieved chunk match this section?” on a fixed set of noisy pages.
- Online (if applicable): search/chat quality metrics; regression tests on embedding checksums for golden nodes.
- Ops: fraction of nodes using excerpt vs full page; fraction of successful `embeddings_url` narrowings; error and timeout rates.

## 11. Implementation notes (for future PRs)

- Wire flag in `in_memory_embeddings.generate_embeddings` / `get_content` path without breaking incremental embedding comparisons.
- Ensure **`hyperlink`** is never written by the smart-extract path; only **`embeddings_url`** (and embedding vectors / `embeddings_content`) on the `Embeddings` row (and any explicitly approved node columns if added later—default is embeddings table only).
- Add tests: same URL, two different `section_key`s → two different excerpts; fragment exists vs does not exist; `shadow` produces logs without changing stored vectors.

### 11.1 Implemented (code map)

- **`CRE_EMBED_SMART_EXTRACT`:** `on` (default) | `off` | `shadow`.
- **`CRE_EMBED_SMART_CONFIDENCE`:** minimum model confidence (default `0.65`).
- **`CRE_EMBED_ALIGN_MODEL`:** OpenAI chat model for alignment JSON (default `gpt-4o-mini`).
- **`CRE_EMBED_SMART_MIN_EXCERPT_CHARS`:** minimum excerpt length before fallback (default `30`).
- **`CRE_EMBED_FRAGMENT_ID_DENYLIST`:** comma-separated extra `id` values to ignore for fragments.
- Code: `application/prompt_client/embed_alignment.py`, wiring in `prompt_client.py`, `align_embedding_span_json` on OpenAI and Vertex clients, `Node_collection.add_embedding(..., embeddings_url=...)`.
- Tests: `application/tests/embed_alignment_test.py`, `application/tests/prompt_client_smart_embed_test.py`; live LLM + network: `application/tests/test_smart_embeddings_e2e_llm.py` (`pytest -m llm_e2e`, requires `OPENAI_API_KEY` or `GEMINI_API_KEY`).
- Full rebuild after logic changes: `python cre.py --regenerate_embeddings --cache_file ./standards_cache.sqlite` (deletes all embedding rows, then re-embeds everything).

## 12. References

- `application/prompt_client/prompt_client.py` — `get_content`, `generate_embeddings`, `in_memory_embeddings`
- `application/database/db.py` — `Node`, `Embeddings.embeddings_url`
