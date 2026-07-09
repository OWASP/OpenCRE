# RFC: Opportunistic Local Gap Analysis Fetch from Production

---

## Status

**Draft — agent-ready implementation spec**

This document is the detailed implementation specification referenced by [issue #534](https://github.com/OWASP/OpenCRE/issues/534). It supersedes bulk GA download via `--upstream_sync` as the primary local-dev path. Production (opencre.org) remains **cache-only**; local instances fetch precomputed material rows on demand.

| Field | Value |
|-------|-------|
| **Status** | Draft (spec-only PR; no production code) |
| **Authors** | OpenCRE maintainers (design approved in #534) |
| **Tracking issue** | [#534 — opportunistic GA fetch from prod](https://github.com/OWASP/OpenCRE/issues/534) |
| **Related issues** | [#471](https://github.com/OWASP/OpenCRE/issues/471) (upstream sync resilience), [#900](https://github.com/OWASP/OpenCRE/pull/900) (parent upstream work) |
| **Related PRs** | [#951](https://github.com/OWASP/OpenCRE/pull/951) (`CRE_UPSTREAM_*` retry pattern to mirror) |
| **Supersedes** | Bulk `download_gap_analysis_from_upstream()` as default local path (function remains internal/dev-only) |
| **Advanced fallback** | JIT Neo4j compute (`CRE_NO_CALCULATE_GAP_ANALYSIS` unset + RQ path) — documented separately; **not** the default UI/REST path |

---

## Problem statement

The gap-analysis (GA) cache is very large (~9 GB). Downloading it wholesale during `--upstream_sync` is unreliable and unnecessary for most local development: contributors typically need only the GA pairs they actually view.

Production (opencre.org) already serves precomputed GA rows from Postgres (cache-only; cache miss → 404). Local instances should reuse that upstream cache **opportunistically** instead of requiring a full bulk sync or triggering expensive Neo4j compute in the request path.

**Current local behavior (to change for non-Heroku):**

- `GET /rest/v1/map_analysis` checks local `gap_analysis_results` SQL cache.
- On miss, non-Heroku instances enqueue RQ/Neo4j compute (`job_id` response) or fall back to synchronous compute.
- `download_gap_analysis_from_upstream()` exists but is explicitly **not** exposed to CLI/REST and downloads all pairs (~10 GB).

**Target behavior:**

On cache miss with auto-fetch enabled, fetch the **full material row** from prod, upsert locally, serve it. No UI-triggered compute on miss.

---

## Goals

1. **Single backend code path** for UI and `GET /rest/v1/map_analysis` (and drill-down endpoints that share the same cache layer).
2. **Opportunistic prod fetch** on local cache miss — one pair at a time, read-only HTTP.
3. **V1 cache policy:** once cached locally, always serve from local cache (no automatic prod re-fetch).
4. **Concurrency control:** single in-flight fetch per pair; concurrent requests see **download in progress**.
5. **Clear miss UX:** prod 404 → documented backfill instructions; prod down → try again (not hidden compute).
6. **Independence** from `--upstream_sync` CRE graph sync; failed fetches never overwrite existing local material rows.
7. **Configurable** via env vars mirroring `CRE_UPSTREAM_*` from [#951](https://github.com/OWASP/OpenCRE/pull/951).
8. **Test coverage** for fetch, upsert, lock, 404 paths, env disable, soft-message detection, V1 no re-fetch.

## Non-goals

| Item | Notes |
|------|-------|
| Bulk GA download via `--upstream_sync` | Superseded; `download_gap_analysis_from_upstream()` stays internal |
| GA compute on production | Prod remains cache-only (see `AGENTS.md`) |
| GA compute in UI/request path on cache miss | Blocked; backfill via docs/CLI only |
| JIT Neo4j compute as default | Advanced fallback in docs only |
| V2 TTL / force-refresh | Deferred (see Cache policy) |
| Prescribing exact Makefile targets in implementation | Operational docs PR covers steps |
| Auth on prod fetch | Read-only public REST endpoints |

---

## Design

All numbered decisions below are **maintainer-approved** in #534. Implementers must not reinterpret them.

### D1 — Trigger: shared backend path

Both the Gap Analysis **UI** (`application/frontend/src/pages/GapAnalysis/GapAnalysis.tsx` → `GET /rest/v1/map_analysis`) and direct **REST** clients use the **same** backend fetch/cache function. Extract shared logic from `map_analysis()` in `application/web/web_main.py` into a dedicated module (e.g. `application/utils/ga_upstream_fetch.py`) callable from the route and from tests.

**Heroku guard unchanged:** `_is_heroku_deploy()` continues to serve cache-only; cache miss → 404. This RFC applies to **local / non-Heroku** instances only.

### D2 — Prod URL and failure behavior

| Condition | Local material row exists? | Response |
|-----------|---------------------------|----------|
| Cache hit | yes | `200` + `{"result": ...}` from local SQL |
| Cache miss, auto-fetch enabled, prod `200` | — | Upsert row, `200` + result |
| Cache miss, fetch in flight | — | `202` or `200` + `{"status": "in_progress"}` (see API section) |
| Prod unreachable after retries exhausted | yes | `200` + local cached row |
| Prod unreachable after retries exhausted | no | Error payload + **Try again** CTA; links to backfill docs |
| Prod `404` (pair not in prod cache) | no | Error payload + backfill instructions; **no** UI compute |
| `CRE_GA_NO_UPSTREAM=1` | no | Error payload + backfill instructions; no prod call |

**Do not** silently fall back to Neo4j/RQ compute in the UI/request path when prod is down or returns 404. Local compute remains CI/docs-only (existing `CRE_NO_CALCULATE_GAP_ANALYSIS` + RQ path is **not** the default miss handler after this RFC lands).

**Prod base URL:** `CRE_GA_UPSTREAM_API_URL` — default `https://opencre.org/rest/v1`. GA fetch uses `GET {base}/map_analysis?standard={a}&standard={b}`.

### D3 — Persist: full material row upsert

Fetch the prod response body; wrap as `{"result": <prod result>}` JSON string (matching existing `gap_analysis_results.ga_object` shape). Upsert via `Node_collection.add_gap_analysis_result()` which already enforces `should_persist_primary_gap_analysis_cache()` — non-material payloads must not overwrite material rows.

Mirror material-row detection from `application/utils/gap_analysis.py`:

- `primary_gap_analysis_payload_is_material()`
- `gap_analysis_cache_key_is_primary()`
- Cache key: `gap_analysis.make_resources_key([standard_a, standard_b])` → `"A >> B"`

Reference: `scripts/sync_gap_analysis_table.py` upsert semantics (material rows only).

### D4 — Concurrency: single fetch per pair

Use an in-process or Redis-backed lock keyed by `ga:upstream:inflight:{cache_key}` (parallel to existing `ga:inflight:{cache_key}` for RQ jobs, but **separate namespace** to avoid collision).

| State | Behavior |
|-------|----------|
| No local row, no in-flight fetch | Start prod fetch; set in-flight lock |
| In-flight fetch exists | Return **download in progress** (do not start second fetch) |
| Fetch completes successfully | Upsert row, clear lock, return result |
| Fetch fails | Clear lock; apply D2 failure table |

Lock TTL: at least `CRE_GA_UPSTREAM_TIMEOUT_SECONDS * CRE_GA_UPSTREAM_MAX_ATTEMPTS + buffer` (e.g. 150s default).

### D5 — Prod 404 UX

When prod returns `404` after retries (or immediate 404 for definitive miss — **do not retry 404**), and no local material row exists:

1. Return structured error (HTTP `404`) with stable `error_code` (e.g. `ga_cache_miss`).
2. Include **backfill instructions** with links:
   - OpenCRE site docs (opencre.org — URL TBD in Phase 4 docs PR)
   - GitHub repo docs (`docs/` or `AGENTS.md` operational section)
3. **Do not** trigger local GA compute from UI.

Exact copy is implementation-defined but must be stable enough for frontend tests. Suggested structure:

```json
{
  "error_code": "ga_cache_miss",
  "message": "This gap analysis pair is not cached locally or on opencre.org.",
  "backfill_docs_url": "https://github.com/OWASP/OpenCRE/blob/main/docs/...",
  "try_again": false
}
```

### D6 — Backfill documentation

A separate docs PR (Phase 4) writes operational instructions. This RFC does **not** prescribe Makefile targets. Docs must cover:

- Local backfill via `scripts/backfill_gap_analysis.sh` / `make backfill-gap-analysis` (reference only)
- `scripts/sync_gap_analysis_table.py` for bulk copy between DBs
- Advanced JIT Neo4j fallback (explicit opt-in, not default)

### D7 — Soft message: file-a-ticket CTA

When **all three** conditions hold, append a soft CTA to file a GitHub issue after the standard backfill instructions:

| # | Condition | How to verify |
|---|-----------|---------------|
| 1 | Both standards exist locally in CRE graph | Node lookup succeeds for both standard names |
| 2 | Both are valid GA participants | `GET /rest/v1/ga_standards` (local) includes both **or** individual standard GET against prod succeeds **or** local graph metadata marks them GA-eligible |
| 3 | Prod GA request for this pair returns `404` or terminal error after retries | Upstream `map_analysis` exhausted |

When any condition fails, show **only** standard backfill instructions (no soft CTA).

Suggested addition to error payload:

```json
{
  "soft_cta": {
    "show": true,
    "message": "Both standards appear valid for gap analysis but this pair is missing from opencre.org. Consider filing an issue.",
    "issue_url": "https://github.com/OWASP/OpenCRE/issues/new"
  }
}
```

### D8 — Refresh and logging

- Backend owns fetch lifecycle; frontend refresh/poll sees the same in-progress or final state.
- **Log at INFO** when a local instance successfully pulls a pair from prod:
  - `logger.info("GA upstream fetch: pulled pair %s from %s", cache_key, upstream_base_url)`

### D9 — Env disable flag

`CRE_GA_NO_UPSTREAM=1` (or `true`/`yes`, case-insensitive) disables auto-fetch entirely. On cache miss: return backfill instructions (same as D5) without calling prod. Document in `.env.example`.

Existing `CRE_NO_CALCULATE_GAP_ANALYSIS` remains separate — it disables **local** compute scheduling during import; do not conflate the two flags.

### D10 — Independence from `--upstream_sync`

GA auto-fetch is **orthogonal** to CRE graph upstream sync (`--upstream_sync`, `fetch_upstream_json`, `CRE_UPSTREAM_*`). Locally cached GA pairs:

- Are **preserved** across CRE sync operations.
- Are **not overwritten** by a failed prod fetch (`should_persist_primary_gap_analysis_cache`).

### D11 — Security

- **Read-only** HTTP client: `GET` only to prod GA endpoints.
- **No authentication** headers sent to prod (public endpoints).
- **No writes** to prod.
- No user-supplied URL injection: `CRE_GA_UPSTREAM_API_URL` is operator-configured env only; standard names come from existing validated request parsing.

### D12 — Configurable prod fetch (env vars)

GA upstream HTTP client uses `CRE_GA_UPSTREAM_*`, scoped parallel to `CRE_UPSTREAM_*` in `application/cmd/cre_main.py` (`fetch_upstream_json`).

Implement `fetch_ga_upstream_json(path, ...)` or generalize `fetch_upstream_json` with a `prefix="CRE_GA_UPSTREAM"` parameter. Retry semantics must match #951:

- Retry transient network errors and HTTP `5xx`, `429`
- **Do not retry** `404` or other `4xx` (except `429`)
- Honor `Retry-After` on `429`
- Linear backoff: `CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS * attempt`

---

## Environment variable reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CRE_GA_UPSTREAM_API_URL` | `https://opencre.org/rest/v1` | Prod REST base URL for GA fetch |
| `CRE_GA_UPSTREAM_TIMEOUT_SECONDS` | `30` | Per-request timeout (Heroku-typical) |
| `CRE_GA_UPSTREAM_MAX_ATTEMPTS` | `4` | Max retry attempts before surfacing failure |
| `CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS` | `2` | Base backoff multiplier between retries |
| `CRE_GA_NO_UPSTREAM` | unset (auto-fetch **on**) | Set to `1`/`true`/`yes` to disable prod auto-fetch |

**Parity reference (`CRE_UPSTREAM_*` — CRE graph sync only, not GA fetch):**

| Variable | Default |
|----------|---------|
| `CRE_UPSTREAM_API_URL` | `https://opencre.org/rest/v1` |
| `CRE_UPSTREAM_TIMEOUT_SECONDS` | `30` |
| `CRE_UPSTREAM_MAX_ATTEMPTS` | `4` |
| `CRE_UPSTREAM_RETRY_BACKOFF_SECONDS` | `2` |

All new GA vars must be documented in `.env.example` during Phase 1.

---

## API and UI behavior

### Fetch flow (local, non-Heroku)

```
Request: GET /rest/v1/map_analysis?standard=A&standard=B
                │
                ▼
        Local material row in gap_analysis_results?
                │
       yes ─────┴───── no
        │              │
        ▼              ▼
   Return 200     CRE_GA_NO_UPSTREAM set?
   {result}              │
                  yes ───┴─── no
                   │          │
                   ▼          ▼
              404 + docs   In-flight lock for pair?
                              │
                     yes ────┴──── no
                      │              │
                      ▼              ▼
              in_progress      Start prod GET
              response         map_analysis
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                        200       404     unreachable
                          │         │         │
                     upsert+200   404+docs  local row?
                                              │
                                     yes ────┴──── no
                                      │              │
                                      ▼              ▼
                                  200+cache    try_again+docs
```

### Response shapes

**Success (cached or freshly fetched):**

```json
HTTP 200
{"result": { ... }}
```

**Download in progress** (concurrent requests while fetch runs):

```json
HTTP 202
{
  "status": "in_progress",
  "cache_key": "A >> B",
  "poll_after_seconds": 2
}
```

Frontend (`GapAnalysis.tsx`) must handle `status: "in_progress"` alongside existing `job_id` polling. Poll the **same** `map_analysis` endpoint (not `ma_job_results`) when `in_progress` is returned. Remove or gate legacy RQ `job_id` path for the default miss flow.

**Prod down / exhausted retries, no local row:**

```json
HTTP 503
{
  "error_code": "ga_upstream_unavailable",
  "message": "Could not reach opencre.org to fetch this gap analysis.",
  "try_again": true,
  "backfill_docs_url": "..."
}
```

**Prod 404, no local row:**

```json
HTTP 404
{
  "error_code": "ga_cache_miss",
  "message": "...",
  "try_again": false,
  "backfill_docs_url": "...",
  "soft_cta": { "show": true|false, ... }
}
```

### Drill-down endpoints

`GET /rest/v1/map_analysis_weak_links` and subresource keys (`make_subresources_key`) are **out of scope for v1 upstream fetch** unless explicitly extended in a follow-up. V1 upstream fetch covers **primary directed pairs** (`A >> B`) only.

### OpenCRE fast path

Existing OpenCRE overlap fast path in `map_analysis()` (PR #825) remains unchanged and takes precedence before upstream fetch.

---

## Cache policy

### V1 (this RFC)

Once a pair is cached locally with a **material** payload:

- Subsequent requests serve from local SQL **without** calling prod.
- No TTL, no `Cache-Control` revalidation, no background refresh.
- Tests must assert: second request does **not** invoke prod HTTP (mock call count = 1).

### V2 (future — out of scope)

Add TTL-based re-fetch from prod (env-controlled staleness window, e.g. `CRE_GA_UPSTREAM_TTL_SECONDS`). Document as Version 2; do not implement in v1.

---

## Security

| Concern | Mitigation |
|---------|------------|
| Prod write access | GET-only client; no POST/PUT/DELETE |
| Credential leakage | No auth headers; no secrets in GA upstream env vars |
| SSRF via user input | Standard names validated; base URL from env only |
| Cache poisoning | `should_persist_primary_gap_analysis_cache` rejects non-material overwrites |
| Resource exhaustion | Single in-flight fetch per pair; timeout + max attempts |

---

## Dependencies

| Dependency | Status |
|------------|--------|
| Prod `GET /rest/v1/map_analysis` serving material rows | Existing on opencre.org |
| Local `gap_analysis_results` table + upsert | Existing (`application/database/db.py`) |
| `CRE_UPSTREAM_*` retry pattern | Landed in #951 — mirror for `CRE_GA_UPSTREAM_*` |
| `scripts/sync_gap_analysis_table.py` | Existing bulk copy tool (orthogonal) |
| Phase 4 docs PR | To be written |

**Independence:** GA auto-fetch does not require `--upstream_sync` to have run. CRE graph should contain the two standards for meaningful GA results, but fetch/upsert mechanics are independent.

---

## Implementation ladder

Each phase has explicit **GATE** criteria. Do not start Phase N+1 until Phase N gate passes.

### Phase 0 — Spec approved (this PR)

**Deliverable:** This RFC merged to `main`.

**Gate criteria:**

- [ ] Maintainers approve RFC content
- [ ] Issue #534 updated with link to spec PR
- [ ] `make lint` passes (markdown only)

---

### Phase 1 — Backend fetch + upsert + lock

**Deliverable:** `application/utils/ga_upstream_fetch.py` (or equivalent) with:

- `fetch_ga_upstream_json()` — retrying GET client (`CRE_GA_UPSTREAM_*`)
- `resolve_gap_analysis_pair(standards, database)` — cache check → lock → fetch → upsert
- In-flight lock (Redis preferred for multi-worker; in-process acceptable for single-worker dev)
- Unit tests in `application/tests/ga_upstream_fetch_test.py`

**Files to create/modify:**

| File | Change |
|------|--------|
| `application/utils/ga_upstream_fetch.py` | **New** — core fetch/lock/upsert logic |
| `application/tests/ga_upstream_fetch_test.py` | **New** — unit tests |
| `.env.example` | Add `CRE_GA_*` vars |

**Gate criteria (automated):**

- [ ] `make lint` — pass
- [ ] `make mypy` — pass
- [ ] `make test` — pass, including new module
- [ ] Unit tests: mocked prod `200` → upsert called with material payload
- [ ] Unit tests: mocked prod `404` → no upsert, structured error
- [ ] Unit tests: concurrent calls → second returns `in_progress`, single HTTP call
- [ ] Unit tests: fetch failure with existing local row → returns local row, row unchanged
- [ ] Unit tests: fetch failure without local row → `try_again: true`, no upsert
- [ ] Unit tests: `CRE_GA_NO_UPSTREAM=1` → no HTTP call
- [ ] Unit tests: env defaults (`timeout=30`, `max_attempts=4`)
- [ ] Unit tests: V1 no re-fetch — cached pair served, prod mock call count unchanged
- [ ] Unit tests: non-material prod response does not overwrite existing material row

**Gate criteria (manual):**

- [ ] Local Flask shell / curl: miss pair triggers prod fetch and populates `gap_analysis_results`

---

### Phase 2 — REST GA integration

**Deliverable:** Wire `resolve_gap_analysis_pair()` into `map_analysis()` for non-Heroku path. Replace default RQ enqueue on miss with upstream fetch (RQ remains available for explicit import/backfill flows, not default UI miss).

**Files to modify:**

| File | Change |
|------|--------|
| `application/web/web_main.py` | Call shared resolver; map response shapes |
| `application/tests/web_gap_analysis_test.py` (or extend existing web tests) | Integration tests for route |

**Gate criteria (automated):**

- [ ] `make lint`, `make mypy`, `make test` — pass
- [ ] Route test: cache hit → 200, no upstream call
- [ ] Route test: cache miss → in_progress → 200 after fetch
- [ ] Route test: Heroku deploy mock → still 404 on miss (no regression)
- [ ] Route test: `CRE_GA_NO_UPSTREAM=1` → 404 + docs payload

**Gate criteria (manual):**

- [ ] `curl localhost:5000/rest/v1/map_analysis?standard=X&standard=Y` matches UI behavior

---

### Phase 3 — Frontend in-progress + 404 + try-again UX

**Deliverable:** Update `GapAnalysis.tsx` (and `LoadingAndErrorIndicator` if needed) to:

- Poll on `status: "in_progress"` (same endpoint)
- Render backfill docs link on `ga_cache_miss`
- Render **Try again** button on `ga_upstream_unavailable`
- Render soft CTA when `soft_cta.show === true`

**Files to modify:**

| File | Change |
|------|--------|
| `application/frontend/src/pages/GapAnalysis/GapAnalysis.tsx` | Poll + error UX |
| Frontend tests (if present) or manual checklist | UX verification |

**Gate criteria (automated):**

- [ ] `make lint` — pass
- [ ] `make frontend` — pass (production build)

**Gate criteria (manual):**

- [ ] Select uncached pair → "downloading" state → results render
- [ ] Prod 404 pair → backfill message + optional soft CTA
- [ ] Simulated prod down → Try again button works
- [ ] `CRE_GA_NO_UPSTREAM=1` → backfill message, no spinner hang

---

### Phase 4 — Operational documentation

**Deliverable:** User-facing docs for local GA backfill (opencre.org and/or `docs/` in repo).

**Content must include:**

- Opportunistic fetch behavior (default)
- `CRE_GA_NO_UPSTREAM` and `CRE_GA_UPSTREAM_*` env vars
- When to use `make backfill-gap-analysis` / `scripts/backfill_gap_analysis.sh`
- When to use `scripts/sync_gap_analysis_table.py`
- Advanced JIT Neo4j compute (explicit opt-in, not default)
- Prod cache-only model (`AGENTS.md` cross-link)

**Gate criteria:**

- [ ] Docs merged and linked from RFC + `.env.example`
- [ ] URLs in Phase 2/3 error payloads point to real doc anchors

---

### Phase 5 — Tests + CI hardening

**Deliverable:** Full test matrix green; soft-message positive/negative cases; logging assertion.

**Gate criteria (automated):**

- [ ] `make lint` — pass
- [ ] `make mypy` — pass
- [ ] `make test` — full suite pass
- [ ] Soft CTA: positive case (all 3 conditions) → `soft_cta.show: true`
- [ ] Soft CTA: negative cases (missing local standard, non-GA participant) → `soft_cta.show: false`
- [ ] Log assertion: successful prod pull emits INFO log line
- [ ] CI green on PR

---

## Build and test ladder

Run in order after each phase:

```bash
make lint
make mypy
make test                                    # full suite before merge
python -m unittest application/tests/ga_upstream_fetch_test.py   # targeted during Phase 1
python -m unittest application/tests/web_gap_analysis_test.py    # targeted during Phase 2 (if created)
make frontend                                # Phase 3 only
```

### New unit tests (Phase 1+)

| Test | Asserts |
|------|---------|
| `test_fetch_success_upserts_material_row` | Mock prod 200 → `add_gap_analysis_result` called once with material JSON |
| `test_fetch_404_no_upsert` | Mock prod 404 → no DB write; error dict returned |
| `test_fetch_404_no_retry` | Mock prod 404 → HTTP call count = 1 |
| `test_concurrent_in_progress` | Two parallel resolves → one HTTP call; second returns `in_progress` |
| `test_prod_down_serves_local_cache` | Mock ConnectionError after retries + local row exists → 200 from cache |
| `test_prod_down_try_again` | Mock ConnectionError + no local row → `try_again: true` |
| `test_no_upstream_flag_skips_http` | `CRE_GA_NO_UPSTREAM=1` → zero HTTP calls |
| `test_env_defaults` | Unset env → timeout 30, max_attempts 4 |
| `test_v1_no_refetch` | Pre-seeded cache → resolve → HTTP mock not called |
| `test_failed_fetch_preserves_cache` | Bad prod response + existing row → row bytes unchanged |
| `test_soft_cta_positive` | Both standards local + GA-eligible + prod 404 → `soft_cta.show` |
| `test_soft_cta_negative_missing_standard` | One standard missing locally → no soft CTA |
| `test_soft_cta_negative_non_participant` | Standard not in ga_standards → no soft CTA |
| `test_success_logs_upstream_pull` | caplog captures INFO upstream fetch message |
| `test_read_only_get` | Client never calls post/put/patch/delete |

### Manual testing checklist

Prerequisites: local OpenCRE running with Postgres, CRE graph imported (not full GA cache), `CRE_GA_NO_UPSTREAM` unset.

1. **Baseline cache miss → prod fetch**
   - [ ] Pick two GA-eligible standards not in local `gap_analysis_results`
   - [ ] Open Gap Analysis UI, select pair
   - [ ] Observe in-progress state, then results
   - [ ] Verify row in DB: `SELECT cache_key FROM gap_analysis_results WHERE cache_key LIKE '% >> %'`
   - [ ] Check server logs for `GA upstream fetch: pulled pair`

2. **V1 no re-fetch**
   - [ ] Repeat same pair request
   - [ ] Confirm fast response (no prod delay)
   - [ ] (Optional) tcpdump or mock proxy: no second call to opencre.org

3. **Prod 404**
   - [ ] Request pair known missing on prod (or mock upstream 404)
   - [ ] UI shows backfill instructions link
   - [ ] No RQ job started

4. **Soft CTA**
   - [ ] With both standards local and GA-eligible, request prod-missing pair
   - [ ] Soft "file a ticket" message appears

5. **Prod down simulation**
   - [ ] Set `CRE_GA_UPSTREAM_API_URL=http://127.0.0.1:1` (unreachable)
   - [ ] Uncached pair → Try again UI
   - [ ] Cached pair (from step 1) → still serves from local cache

6. **Disable flag**
   - [ ] `CRE_GA_NO_UPSTREAM=1`, restart app
   - [ ] Uncached pair → backfill message, no prod attempt

7. **REST parity**
   - [ ] `curl` same pair → identical status codes and JSON shape as UI

---

## Acceptance criteria

Verifiable checklist derived from #534. All must pass before closing the implementation issue.

- [ ] UI and local REST GA API share one backend fetch/cache code path (`resolve_gap_analysis_pair` or equivalent)
- [ ] Configurable prod base URL (`CRE_GA_UPSTREAM_API_URL`, default opencre.org); read-only prod HTTP client (GET only, no auth, no writes)
- [ ] On cache miss with auto-fetch enabled: fetch full material row from prod and upsert locally
- [ ] **V1 cache policy:** once cached locally, subsequent requests serve from local cache without prod re-fetch
- [ ] On prod unreachable (after `CRE_GA_UPSTREAM_MAX_ATTEMPTS` retries): serve local cached row if present; otherwise Try again + backfill docs link (no UI compute)
- [ ] On prod 404 for pair not in local cache: backfill instructions (opencre.org + GitHub links); no local compute from UI
- [ ] Single in-flight fetch per pair; concurrent requests get `in_progress`; frontend polls same endpoint
- [ ] Soft CTA when soft-message detection (D7) conditions met
- [ ] `CRE_GA_NO_UPSTREAM=1` disables auto-fetch; documented in `.env.example`
- [ ] `CRE_GA_UPSTREAM_TIMEOUT_SECONDS` default **30**; `CRE_GA_UPSTREAM_MAX_ATTEMPTS` default **4**; documented in `.env.example`
- [ ] Failed fetch does not overwrite existing local material cached row
- [ ] INFO logging when local instance pulls pair from prod
- [ ] Tests: mocked prod HTTP, cache upsert, in-progress lock, 404 UX, env disable, read-only client, logging, env defaults, soft-message positive/negative, V1 no re-fetch

---

## Out of scope (explicit)

- **V2 TTL** — automatic prod re-fetch for stale local rows
- **UI-triggered local compute** on cache miss (Neo4j/RQ in request path)
- **Bulk ~9 GB download** via `--upstream_sync` or exposed CLI
- **GA compute on production** — prod stays cache-only
- **Subresource / weak-links upstream fetch** — primary pairs only in v1
- **Authentication** to prod GA endpoints

---

## Key code references

| Area | Path |
|------|------|
| Current GA route | `application/web/web_main.py` — `map_analysis()` |
| GA cache helpers | `application/utils/gap_analysis.py` |
| SQL upsert | `application/database/db.py` — `add_gap_analysis_result()` |
| Bulk sync script | `scripts/sync_gap_analysis_table.py` |
| CRE upstream retry (#951) | `application/cmd/cre_main.py` — `fetch_upstream_json()` |
| Internal bulk GA download (do not expose) | `application/cmd/cre_main.py` — `download_gap_analysis_from_upstream()` |
| Frontend GA page | `application/frontend/src/pages/GapAnalysis/GapAnalysis.tsx` |
| Prod GA ops | `AGENTS.md` — gap analysis section |

---

## Agent implementation notes

1. **Read this RFC and #534** before claiming the implementation issue.
2. **Do not implement on Heroku** — guard `_is_heroku_deploy()` must remain.
3. **Mirror #951 retry semantics** — reuse patterns, separate env prefix.
4. **Test-first** per `tdd-workflow.mdc` — Phase 1 tests before route wiring.
5. **Minimal diff** — extract shared function; do not refactor unrelated GA compute paths.
6. **Judge review** required before merge of implementation PRs (substantive change).
7. **No commits** unless explicitly requested by issue assignee/maintainer.
