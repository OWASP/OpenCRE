# RFC: User Authentication and Personal MyOpenCRE Views

**Author:** Saatwik Kumar Yadav  
**Status:** Draft — submitted for community review  
**Related issues:** #375, #585, #586

---

## Context

MyOpenCRE currently runs locally only. Users who want automated CRE mappings must run their own OpenCRE instance, which requires Docker, a local database, and significant technical setup. This RFC proposes making MyOpenCRE available online with user login, so any authenticated user can upload a standard and receive automated CRE mappings stored against their account.

**What MyOpenCRE currently does (existing endpoints):**
- `GET /rest/v1/cre_csv` — downloads a CSV template of all existing CREs
- `POST /rest/v1/cre_csv_import` — accepts a filled CSV and imports mappings into the local database

Both endpoints require no authentication and operate only on a locally-running instance. There is no way for a user to upload a standard and receive automated mappings without running OpenCRE themselves. This RFC adds that capability via authenticated endpoints under `/rest/v2/`.

The current codebase already has Google OAuth plumbing (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `login_required` decorator, `LOGIN_ALLOWED_DOMAINS`). What does not exist is any persistent `User` model or user-scoped data. This RFC adds that persistence and wires it to a new MyOpenCRE mapping flow.

**Core constraints:**
- No data duplication: user sections point to shared CRE nodes by ID; nothing in the CRE graph is copied
- No per-user embedding storage: section text is encoded ephemerally at upload time; only the mapping result is persisted
- All new authenticated endpoints live under `/rest/v2/`
- rq is already present in the repo; this RFC reuses that infrastructure for mapping jobs

---

## Implementation order

1. **User identity first** — nothing else works without knowing who the user is
2. **Schema and storage second** — rows need to exist before the mapping engine writes to them
3. **Mapping execution third** — build and test the core logic before wiring it to HTTP
4. **Upload endpoint fourth** — wire the mapping logic to a real HTTP request
5. **Result retrieval fifth** — expose what the mapping engine produced

**Note:** TODO 3 (mapping engine) is written to be fully testable with fixture data before any real HTTP upload exists, so it can also be built and validated in parallel with TODOs 1–2 if preferred.

---

## TODO 1 — User identity persistence

**What to build:**  
A `User` SQLAlchemy model, three auth routes, and session binding.

**Code changes:**
- Add `User` model to `application/database/db.py`:
  ```
  users
    id            UUID, primary key
    google_sub    TEXT, NOT NULL, UNIQUE
    email         TEXT, NOT NULL
    display_name  TEXT
    created_at    TIMESTAMP WITH TIME ZONE
    last_seen_at  TIMESTAMP WITH TIME ZONE
  ```
  `google_sub` is used as the identity anchor because it is immutable; email can change and would silently break identity if used instead.

- Add to `application/web/web_main.py`:
  - `GET /auth/login` → redirect to Google consent; store `next` URL in session
  - `GET /auth/callback` → look up or create `User` by `google_sub`; write only `user_id` to Flask session; redirect to `next`
  - `GET /auth/logout` → clear session; redirect to `/`
- Update `login_required` decorator to redirect to `/auth/login?next=<current_url>`
- Session stores only `user_id` (UUID). Display name looked up on demand.
- Session duration: 30-day sliding window, configurable via `SESSION_LIFETIME_DAYS` env var

**Tests:**
- New user → exactly one row in `users`, correct `google_sub`
- Same user logs in again → no new row, `last_seen_at` updated
- Session cookie contains only `user_id` after login
- `/auth/logout` clears session; next request is anonymous
- `login_required` returns 302 for anonymous, 200 for authenticated
- `LOGIN_ALLOWED_DOMAINS` blocks unlisted domains when set
- Concurrent login from 10 users produces no duplicate rows

**Checkpoint — pass criteria:**
- Repeat login does not create a duplicate user row
- Auth-protected endpoint resolves current user reliably
- All tests above green on CI

**Failure / rollback:**
- Forged or expired OAuth state → 400, no session set
- Google returns `sub` but no email → create user, log warning, display UUID
- DB failure during callback → 503, no session set

---

## TODO 2 — User-owned standard and section storage

**What to build:**  
Schema and DB access methods for user-owned standards and their sections.

**Code changes:**
- Add two models to `application/database/db.py`:

  ```
  user_standards
    id            UUID, primary key
    user_id       UUID, NOT NULL, FK → users.id ON DELETE CASCADE
    name          TEXT, NOT NULL
    created_at    TIMESTAMP WITH TIME ZONE
    updated_at    TIMESTAMP WITH TIME ZONE
    UNIQUE (user_id, name)

  user_standard_sections
    id            UUID, primary key
    standard_id   UUID, NOT NULL, FK → user_standards.id ON DELETE CASCADE
    section_id    TEXT, NOT NULL
    section_text  TEXT, NOT NULL
    cre_db_id     TEXT, nullable        ← soft reference to shared CRE node
    confidence    REAL, nullable
    status        TEXT, NOT NULL        ← PENDING | AUTO_MAPPED | NEEDS_REVIEW |
                                           UNMAPPABLE | USER_CONFIRMED | USER_REJECTED
    created_at    TIMESTAMP WITH TIME ZONE
    updated_at    TIMESTAMP WITH TIME ZONE
    INDEX (standard_id, status)
    INDEX (standard_id, cre_db_id)
  ```

  `cre_db_id` is a soft reference, not a foreign key. CRE nodes live in the graph layer; a hard FK would couple the two layers. Application validates at write time.

- Add to `Node_collection`:
  - `create_user_standard(user_id, name) → UserStandard`
  - `get_user_standards(user_id) → List[UserStandard]`
  - `upsert_user_standard_sections(standard_id, sections) → None`
  - `get_user_standard_sections(standard_id, user_id) → List[UserStandardSection]`
  - `confirm_section_mapping(section_id, cre_db_id, user_id) → None`
  - `reject_section_mapping(section_id, user_id) → None`

  All methods that read or write user-owned data require `user_id` as a mandatory parameter — a call without `user_id` is a type error, not a runtime check.

**Tests:**
- `create_user_standard` creates one row linked to correct `user_id`
- `create_user_standard` with duplicate name raises unique constraint error
- `get_user_standards` returns only rows for the requesting user
- `upsert_user_standard_sections` creates rows with `status=PENDING`
- `confirm_section_mapping` sets `USER_CONFIRMED` and stores `cre_db_id`
- Two users uploading same-named standards produce separate rows — zero shared state

**Checkpoint — pass criteria:**
- Two users uploading the same-named standard do not share rows
- All six tests green on CI

**Failure / rollback:**
- Upload with duplicate `standard_name` without `overwrite=true` → 409 Conflict
- Upload with `overwrite=true` → delete existing sections, re-import, reset to PENDING
- DB failure mid-upload → transaction rollback; no partial standard row

---

## TODO 3 — Automated mapping execution

**What to build:**  
A standalone mapping function and rq job that takes PENDING sections and produces `cre_db_id` + `confidence` + `status` per section.

**Code changes:**
- Add `application/utils/mapping_job.py`:
  - `run_mapping(standard_id: str, database: Node_collection) → None`
  - Fetch all PENDING sections for `standard_id`
  - Call `model.encode(texts, batch_size=32)` for all sections in one call
  - For each section: pgvector similarity → top-20 candidate CRE nodes → cross-encoder re-rank → keep best result
  - Write `cre_db_id`, `confidence`, `status` back to `user_standard_sections`:
    - `AUTO_MAPPED` if confidence ≥ threshold
    - `NEEDS_REVIEW` if below threshold
    - `UNMAPPABLE` if no candidates returned

- Register `run_mapping` as an rq job (reuses existing rq infrastructure)

- Re-indexing: when the CRE graph is re-indexed, re-run mapping for all sections where `status IN (PENDING, AUTO_MAPPED, NEEDS_REVIEW)`. Never auto-remap `USER_CONFIRMED` — user decisions are ground truth.

**Tests:**
- Upload ASVS fixture → deterministic count of AUTO_MAPPED vs NEEDS_REVIEW vs UNMAPPABLE
- Batch encoding 200 sections completes in under 1 second on CI runner (CPU)
- Re-running mapping on already-mapped sections does not change `USER_CONFIRMED` rows
- rq job is idempotent: killing and restarting worker re-processes only PENDING sections

**Checkpoint — pass criteria:**
- At least one fixture upload (ASVS, WSTG) yields ≥ 98% correct mappings against known CRE links
- Deterministic mapped/unmapped counts on re-run of the same fixture

**Failure / rollback:**
- Model fails to load → job fails immediately, sections stay PENDING, error logged
- OOM during cross-encoder → reduce candidate pool from 20 to 10, retry once
- Worker crash mid-job → job returns to queue; idempotent re-run handles recovery

---

## TODO 4 — Upload endpoint wiring

**What to build:**  
`POST /rest/v2/myopencre/upload` — requires login, creates user standard + pending rows, enqueues mapping job.

**Code changes:**
- Add to `application/web/web_main.py`:

  ```
  POST /rest/v2/myopencre/upload
    requires: login_required
    accepts:  multipart/form-data with cre_csv file + standard_name field
    returns:  202 Accepted + {"standard_id": "...", "job_id": "..."}
  ```

  Route logic:
  1. Validate file is CSV and non-empty; validate `standard_name` present
  2. Check for duplicate `standard_name` for this user → 409 if exists and no `overwrite=true`
  3. Call `create_user_standard(user_id, standard_name)`
  4. Parse CSV using existing `parse_export_format()` — reuse existing parser
  5. Call `upsert_user_standard_sections(standard_id, sections)`
  6. Enqueue `run_mapping(standard_id)` via rq
  7. Return 202

- Add `GET /rest/v2/myopencre/standards/<standard_id>/status`:
  ```json
  {"total": 200, "pending": 145, "mapped": 55, "status": "processing"}
  ```

**Tests:**
- Anonymous POST → 401
- Authenticated POST with valid CSV → 202; DB rows match uploaded section count
- Duplicate `standard_name` without `overwrite=true` → 409
- Duplicate with `overwrite=true` → prior sections deleted, new sections created
- Status endpoint returns correct counts during and after processing
- Status endpoint accessed by a different authenticated user → 403

**Checkpoint — pass criteria:**
- Upload returns `standard_id`; DB rows exactly match uploaded section count
- Status endpoint returns correct in-progress counts while rq job runs

**Failure / rollback:**
- Empty or malformed CSV → 400 with descriptive message; no DB rows created
- DB failure after standard row created but before sections written → rollback entire transaction

---

## TODO 5 — User result retrieval

**What to build:**  
Endpoints for the owner to read mapping results and confirm or reject suggestions.

**Code changes:**
- Add to `application/web/web_main.py`:

  ```
  GET  /rest/v2/myopencre/standards
    requires: login_required
    returns:  list of user's standards with counts per status

  GET  /rest/v2/myopencre/standards/<standard_id>/sections
    requires: login_required + ownership check
    returns:  list of sections with cre_db_id, confidence, status

  POST /rest/v2/myopencre/standards/<standard_id>/sections/<section_id>/confirm
    requires: login_required + ownership check
    body:     {"cre_db_id": "..."}   ← optional override
    effect:   status → USER_CONFIRMED

  POST /rest/v2/myopencre/standards/<standard_id>/sections/<section_id>/reject
    requires: login_required + ownership check
    effect:   status → USER_REJECTED, cre_db_id → null
  ```

- Centralise ownership check in `require_owns_standard(standard_id, user_id)` helper — call at the top of every route that touches a standard.

**Tests:**
- Owner reads their sections → 200 with correct rows
- Another authenticated user reads the same `standard_id` → 403
- Confirm sets `USER_CONFIRMED` + `cre_db_id`
- Reject sets `USER_REJECTED` + clears `cre_db_id`
- Confirm on an already `USER_CONFIRMED` row → idempotent (no error, no change)

**Checkpoint — pass criteria:**
- Owner can read their results
- Any other user gets 403 on the same endpoint
- Safety and regression tests pass

**Failure / rollback:**
- Confirm/reject on non-existent section → 404
- DB failure during confirm → 503, status unchanged

---

## Future work

Gap analysis on user standards (`GET /rest/v2/gap_analysis?user_standard=<id>&compare=ASVS`) is a natural extension once TODO 5 is merged — user section rows already point to shared CRE nodes, so GA requires only a set difference query against the existing GA infrastructure.

---

## Key constraints summary

| Constraint | Decision |
|---|---|
| No per-user embeddings | Encoding is ephemeral; storing vectors wastes space and couples user tables to the shared index |
| `google_sub` as identity anchor | `sub` is immutable; email changes would silently break user identity |
| Soft reference for `cre_db_id` | Hard FK couples user tables to the graph layer; application validates at write time |
| `/rest/v2/` for all new endpoints | Avoids breaking the current API; isolates new auth-required surface |
| `user_id` mandatory on all DB methods | Prevents accidental cross-user reads; a call without `user_id` is a type error |
| `USER_CONFIRMED` never auto-remapped | User decisions are ground truth; graph re-indexing must not silently overwrite them |
| Login required for all uploads | Automated mapping has significant resource cost; no anonymous persisted flow |

---

## Privacy note

This RFC stores user email and display name for the first time (currently nothing is stored, per issue #375). Privacy policy must be updated before production rollout on opencre.org — tracked separately with maintainers, non-blocking for this coding increment.
