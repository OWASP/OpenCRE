## RFC: Incremental, Reviewable Imports for OpenCRE

### 1. Summary

Currently, importing new projects to CRE is a dev-only task that usually takes days of manual effort to check and fix and requires pretty powerful hardware to run on. This is because:
* there are no visal ways to know what changed
* the importing functionality is little more than dev scripts that work for devs but aren't super reliable
* embeddings and gap analysis are flakey

We want to move from fragile, full-graph imports that only a dev can run on a powerful machine to do **incremental, standard-scoped imports** that are **reviewable, cheap to recompute, and safe to apply**.  
Core ideas:

- Treat **each standard as a versioned, independently importable module**.
- Build a **diff engine + staging area** to review changes before they hit the main graph.
- Make **embeddings and gap analysis incremental**, recomputing only what changed.
- Provide an **admin UI / panel** so imports are no longer “single dev on big laptop” operations.

---

### 2. Background & Current Pain

Today:

- **Single dev, heavy machine**: Imports require a powerful dev machine and bespoke scripts.
- **No good scoping**:
  - “Update only ISO” or “bring in latest ASVS” is not straightforward.
  - Fixing a typo in a specific control often requires either:
    - manual DB surgery, or
    - a flaky reimport of the whole standard, risking knocking other things over.
- **Graph structure changes are dangerous**:
  - Introducing a new CRE or changing relationships can force a full reimport.
  - Effects of structural changes aren’t visible beforehand.
- **Expensive recomputation**:
  - Embeddings and gap analysis often have to be recomputed broadly.
  - This duplicates work and increases AI/compute costs.
- **No review surface**:
  - No graphical way to see “before vs after” of an import.
  - No obvious way to preview how new CREs affect the existing graph.

We want a design that **decouples ingestion, review, and application**, and **scopes compute to the minimal affected set**.

---

### 3. Goals & Non-Goals

#### 3.1 Goals

- **Per-standard imports**:
  - Import or reimport a single standard (`ISO`, `ASVS`, etc.) using existing methods:
    - spreadsheet
    - remote JSON
    - custom import modules.
- **Incremental embedding updates**:
  - Detect what changed in the standard and **regenerate embeddings only for those nodes/edges**.
- **Graphical change review**:
  - A **UI to visualize the diff** between current graph and proposed changes.
  - Ability to approve/reject and apply imports to the main graph.
- **Structural change feedback**:
  - If a change introduces/modifies CREs or relationships, **visual indicator of affected subgraph**.
- **Incremental gap analysis**:
  - When structure changes (e.g., new/changed CRE), **recompute gap analysis only for affected parts**.
- **Operationalize imports**:
  - Get closer to an **admin panel** where a non-dev operator can:
    - upload/import
    - review changes
    - apply them
  - Without requiring manual DB surgery or full reimports.

  ** Note **: A full admin panel requires CRE to know of users and is out of scope for this RFC. For this RFC let's hide this functionality behind a variable/feature flag

#### 3.2 Non-Goals (for now)

- Full redesign of the underlying data model.
- Changing the choice of database/vector DB in production immediately (we may **evaluate** alternatives as part of this RFC).
- Fully generic data pipeline framework; this is focused on **OpenCRE’s standards + CRE graph** use case.

---

### 4. High-Level Architecture

At a high level:

1. **Import Orchestrator**:  
   Takes an import request (e.g., “update ISO 27001 from this spreadsheet” or "here's the ASVS json that has CRE mappings"), uses pluggable adapters to parse, and produces a **canonical standard representation** (versioned).

2. **Change Detection & Diff Engine**:  
   Compares the **new canonical standard** against:
   - the previous version of that standard, and
   - the current main graph,
   to generate a **change set** (additions, modifications, deletions of controls, mappings, CREs).

3. **Staging Area / Candidate Graph**:  
   Applies the change set into a **staging graph** (separate tables / schema / DB / Kùzu / etc.).  
   This is where we can:
   - compute **graph diffs**
   - precompute **partial embeddings**
   - run **impact analysis** safely.

4. **Embedding Regeneration Service**:  
   Based on the change set, decide which nodes/edges need new embeddings and run **targeted embedding jobs**. Cache or store embeddings per version.

5. **Impact Analysis & Incremental Gap Engine**:  
   Using the change set and staging graph, identify:
   - which CREs, mappings, and gap-analysis results are affected,
   - recompute **only those** gap-analysis results.

6. **Admin UI / Review Workflow**:  
   A web-based interface where operators can:
   - trigger imports
   - view diffs and impact graphs
   - see cost estimates (e.g., “X nodes will get new embeddings”)
   - approve and apply changes or roll them back.

7. **Apply / Commit Engine**:  
   Once approved, apply the change set to the main graph in a **transactional, idempotent** way, and update associated embeddings and gap analysis.

---

### 5. Modules, Knowledge, Tech & Experiments

Below, each “module” is a conceptual building block. Some may end up as services, some as libraries within the same codebase.

---

#### 5.1 Module A: Import Orchestrator & Standard Versioning

**Responsibility**

- Accept requests like:
  - “Import ASVS v5.0 from this JSON URL”
  - “Reimport ISO 27001 from this spreadsheet”
  ** Note**: These requests DO NOT have to be in natural language (we aren't necessarily creating agents), instead it can be a standard web interface.
- Use existing import methods (spreadsheet, remote JSON, custom modules).
- Normalize into a **canonical intermediate model** for:
  - standard
  - sections
  - controls
  - mappings to CREs.
- Store as **versioned standard snapshots** (e.g., `standard_id`, `version`, `status`).

**Knowledge Needed**

- **Current import scripts**:
  - How they map raw data to current DB tables/objects.
- **Domain model of standards**:
  - How standards, sections, controls, and CREs are represented in the graph today.
- **Versioning strategies**:
  - Semantic versioning vs. timestamp versions vs. git-like content hashes.
  - Strategies for “active” vs. “draft” vs. “archived” versions.

**Tech to Explore**

- **Python orchestration**:
  - `Celery` / `RQ` / `Huey` for background jobs and retries.
- **Schema for canonical representation**:
  - JSON Schema or Pydantic models to tightly define the canonical format.
- **Storage**:
  - PostgreSQL tables for `standard_versions`.
  - Experiment with: lightweight graph dbs like kuzu in case they help with changes.
  - Optionally: store raw import artifacts (original spreadsheet/JSON) in S3/GCS or local storage.

**Experiments / Spikes**

1. **Spike A1**: Wrap an existing import script in a job that:
   - takes a standard identifier + source file/URL,
   - produces a canonical JSON representation,
   - stores it as a `standard_version` row.
2. **Spike A2**: Define and validate a minimal canonical model for one standard (e.g., ASVS), then test round-tripping from import to DB and back.
3. **Spike A3**: Measure runtime and memory footprint for importing a single large standard using this orchestrator to inform resource requirements.

---

#### 5.2 Module B: Standard Adapters & Parsers (Pluggable Import Methods)

**Responsibility**

- Provide **adapter interfaces** for:
  - Spreadsheet sources.
  - Remote JSON APIs.
  - Custom Python modules (e.g., “ASVS importer”).
- Each adapter:
  - reads raw input,
  - maps to the canonical model,
  - handles validation and error reporting.

**Knowledge Needed**

- Current import code (where the logic lives, how it handles errors).
- Differences between standards:
  - some have nested sections, others flat control lists.
  - some embed IDs, others need ID synthesis.

**Tech to Explore**

- **Strategy / plugin pattern** in Python:
  - Abstract base class like `StandardImporter` with methods:
    - `load_source()`
    - `parse()`
    - `to_canonical()`.
- Use **entry points** or a config registry for dynamically discovering importers.
- Validation libraries:
  - `pydantic`, `marshmallow`, or `jsonschema`.

**Experiments / Spikes**

1. **Spike B1**: Implement one `SpreadsheetImporter` and one `JSONImporter` that both output the canonical model for a small test standard.
2. **Spike B2**: Build a small registry that selects the correct importer based on config (e.g., `asvs` uses `ASVSJsonImporter`, `iso27001` uses `SpreadsheetImporter`).
3. **Spike B3**: Log and surface error types suitable for UI (e.g., “row 23 missing ID”) to validate the UX we can provide.

---

#### 5.3 Module C: Change Detection & Diff Engine

**Responsibility**

- Compare:
  - **New standard version (canonical)** vs. **previous version** of that same standard.
  - Identify:
    - added/removed/modified controls
    - changed attributes (title, text, severity)
    - changed mappings to CREs.
- Optionally compare **standard version** vs. **current main graph** to account for manual edits.
- Produce a **machine-readable change set**:
  - e.g. list of `operations`:
    - `ADD_CONTROL`, `UPDATE_CONTROL`, `DELETE_CONTROL`
    - `ADD_MAPPING`, `UPDATE_MAPPING`, `DELETE_MAPPING`.

**Knowledge Needed**

- How controls, standards, and CRE mappings are identified:
  - stable IDs vs. textual matching vs. composite keys.
- Existing DB schema & the rules for “sameness”.
- How manual adjustments are currently made (so the diff logic doesn’t accidentally wipe them).

**Tech to Explore**

- Internal diff library or custom code:
  - For hierarchical data (sections/controls), consider tree diff approach.
- Representation of change sets:
  - JSON patch-like structures vs custom domain-specific operations.

**Experiments / Spikes**

1. **Spike C1**: Implement a diff between two small canonical versions of a standard (e.g., ASVS v4 vs v5) and inspect the resulting operations.
2. **Spike C2**: Simulate a human edit in the main graph (e.g., renamed control) and see how diff logic should behave (ignore? flag conflict?).
3. **Spike C3**: Prototype conflict rules (e.g., if main graph changed since last imported version, require manual resolution).

---

#### 5.4 Module D: Staging Area & Graph Change Review

**Responsibility**

- Provide a **staging layer** where change sets can be:
  - applied,
  - inspected,
  - rolled back,
  - and used for precomputations (embeddings, gap analysis) **without touching the main graph**.
- Expose a way to **visualize diffs**:
  - new nodes/edges
  - modified nodes/edges
  - deleted nodes/edges.

**Knowledge Needed**

- Current graph storage:
- Volume and shape of data:
- Current tools for querying the graph.

**Tech to Explore**

- **Option 1: Same DB, separate schema/tables**:
  - `graph_main` vs `graph_staging`.
- **Option 2: Embedded graph DB**:
  - Investigate **Kùzu** as a local, file-based graph DB for staging/diffs.
- **Visualization / UI**:
  - For front-end:
    - `Cytoscape.js`, `d3.js`, `vis.js`, or `Graphin`.
  - For back-end:
    - APIs to serve diffed node/edge sets.

**Experiments / Spikes**

1. **Spike D1**: Create a small staging schema mirroring key graph tables; apply a synthetic change set and verify it can be queried independently.
2. **Spike D2**: Evaluate Kùzu on a sample subgraph: import a subset of the current graph, run some queries, and measure performance and simplicity.
3. **Spike D3**: Build a minimal graph-diff visualization for one standard’s changes using a JS graph library, fed from a toy API.

---

#### 5.5 Module E: Embedding Regeneration Service (Incremental AI Costs)

**Responsibility**

- Given a change set:
  - decide which nodes/edges/CREs require new embeddings (including impacted neighbors if needed),
  - enqueue targeted embedding jobs,
  - store or update embeddings without recomputing everything.
- Support:
  - “Re-embed only ISO”,
  - “Re-embed controls changed in ASVS v5 vs v4”.

**Knowledge Needed**

- Current embedding strategy:
  - what is embedded (controls, CREs, relationships?)
  - how text is constructed from nodes/edges.
- Where embeddings are stored:
  - database tables, vector DB, file-based.
- Current AI provider & cost profile.

**Tech to Explore**

- Vector DB / storage:
  - `pgvector`, or
  - Qdrant / Weaviate / Chroma.
- Queueing / job management:
  - Celery / RQ tasks that:
    - accept node IDs + text payloads,
    - call the embedding API,
    - update the store.
- Dependency tracking:
  - logic for “if a Standard text is composed from X text, when a control changes, re-embed the control”.

**Experiments / Spikes**
1. **Spike E1**: Given a list of changed control IDs, implement a function that:
   - finds all nodes that depend on those controls,
   - returns a minimal set of IDs to re-embed.
2. **Spike E2**: Run a small benchmark:
   - re-embed 100, 1,000, and 10,000 nodes,
   - measure time and API cost.
3. **Spike E3**: Implement a “dry-run” mode that estimates embedding cost for a given change set without actually calling the API, for UI display.

---

#### 5.6 Module F: Impact Analysis & Incremental Gap Analysis

**Responsibility**

- Given pending changes (especially new/changed CREs and mappings):
  - determine **which parts of the graph and which gap-analysis outputs are affected**,
  - recompute gap analysis **only for those affected regions** in the staging area.
- Determine:
  - impacted standards,
  - impacted CRE groups,
  - impacted gap scores or reports.

**Knowledge Needed**

- Current **gap analysis algorithm**:
  - inputs (graph structure, mappings, embeddings?),
  - outputs (scores per standard, per CRE, per org?).
- How gap results are stored:
  - are they materialized tables, cached in memory, recomputed on demand?

**Tech to Explore**

- Graph query patterns:
  - BFS/DFS from changed CREs to determine affected region.
- **Materialized view strategy**:
  - use DB materialized views or derived tables that can be partially refreshed.

**Experiments / Spikes**

1. **Spike F1**: Given a set of changed CRE IDs, implement a function that:
   - finds all dependent gap-analysis entities (e.g., controls, requirements, scores),
   - lists them as “impacted”.
2. **Spike F2**: Prototype a granular gap recomputation for a small set of CREs and compare runtime vs a full recompute.
3. **Spike F3**: Build a text-only “impact summary”:
   - “Changing CRE X will affect 5 standards, 42 controls, and 3 gap scores” to validate the UX concept.

---

#### 5.7 Module G: Admin UI & User Workflow

**Responsibility**

- A web admin interface that:

  - **Triggers imports**:
    - Select standard, source type, file/URL or module.
  - **Displays import status**:
    - queued, running, failed, completed (staged).
  - **Presents diffs & impact**:
    - list of changed/added/removed controls.
    - graph view of new/removed edges and affected CREs.
    - estimated embedding cost and gap-analysis scope.
  - **Controls application**:
    - approve & apply change set to main graph,
    - rollback or discard staging version.

**Knowledge Needed**

- Existing backend stack:

**Tech to Explore**

- Backend:
  - Extend existing Flask app with `admin/imports` endpoints.
- Frontend:
  - add an “Admin / Imports” section.
  - Graph visualization via Cytoscape.js or similar.
- Auth:
  - integrate with existing auth (JWT, OAuth, etc.) to restrict access.

**Experiments / Spikes**

1. **Spike G1**: Implement a minimal `/admin/imports` API:
   - list import jobs and their status.
2. **Spike G2**: Create a simple UI page that:
   - lists staged imports,
   - links to a simple diff view (even text only).
3. **Spike G3**: Prototype one small graph visualization for a staged import using subset data.

---

#### 5.8 Module H: Apply / Commit Engine & Rollback

**Responsibility**

- Take an **approved change set** and apply it to the main graph safely:
  - ideally in a **single transaction** or a small set of well-defined steps.
- Ensure idempotency:
  - safe to retry if job partially fails.
- Provide **rollback** mechanisms:
  - either by versioning and pointer flip (pointing “current” to previous version),
  - or by inverse operations if practical.

**Knowledge Needed**

- Transaction and locking behavior of current DB.
- How much downtime is acceptable (ideally zero or minimal).
- Capacity for maintaining historical versions vs. in-place updates.

**Tech to Explore**

- Transactional updates:
  - use DB transactions with `SERIALIZABLE` or at least `REPEATABLE READ` isolation for apply operations.
- Versioned writes:
  - consider “append-only with current flag” pattern for nodes/edges.
- Audit logging:
  - store apply operations + who approved them.

**Experiments / Spikes**

1. **Spike H1**: Implement a toy apply of a small change set in a transaction; verify that:
   - main graph moves to new state,
   - staging data remains for audit or is cleaned up as needed.
2. **Spike H2**: Measure impact on query performance when maintaining multiple versions vs. only one.
3. **Spike H3**: Prototype a “rollback last applied import” for a test standard using version pointer flips.

---

#### 5.9 Module I: Ops & Infrastructure (Multi-Machine, Non-Dev Friendly)

**Responsibility**

- Make imports:
  - runnable from **shared infrastructure** (e.g., worker nodes, not just one dev laptop),
  - observable (logs, metrics, alerts),
  - secure (protected admin endpoints).

**Knowledge Needed**

- Current deployment and runtime:
  - where the app runs (GCP, Docker, k8s?),
  - how background tasks are currently handled (if at all).
- Logging/monitoring setup.

**Tech to Explore**

- Background workers:
  - Celery / RQ / Kubernetes Jobs / Cloud Run jobs, depending on existing stack.
- Queues:
  - Redis, RabbitMQ, or GCP Pub/Sub.
- Monitoring:
  - integrate import job metrics into existing monitoring (Prometheus, GCP Monitoring, etc.).

**Experiments / Spikes**

1. **Spike I1**: Run a simple Celery/RQ queue with a “dummy import” job in the current environment.
2. **Spike I2**: Instrument a test import job with timing + memory usage metrics.
3. **Spike I3**: Add structured logging for imports (standard ID, source, version, outcome) and verify they show up in existing log aggregation.

---

### 6. Suggested Learning & Research Topics

Across modules, the team will likely need deeper knowledge in:

- **Graph modeling & versioning**:
  - how to represent multiple versions of a graph, staging vs production, and diffs.
- **Incremental computation patterns**:
  - how to compute deltas for embeddings and gap analysis.
- **Graph visualization**:
  - practical experience with Cytoscape.js / D3 for showing diffs and impacts.
- **Job orchestration / distributed processing**:
  - Celery/RQ, retry semantics, idempotency patterns.
- **Embedding & vector DB best practices**:
  - trade-offs between pgvector and dedicated vector DBs.
- **Domain-specific**:
  - how standards/CRES are currently used by customers to ensure gap analysis behavior matches expectations.

---

### 7. Recommended First Steps

1. **Choose a pilot standard** (e.g., ASVS) and:
   - define its canonical model,
   - wrap its importer under the new Import Orchestrator (Module A + B).
2. **Implement a minimal diff engine** for that standard (Module C) and:
   - print textual diffs for a version-to-version change.
3. **Create a tiny staging area** and:
   - apply one change set there,
   - run a basic impact analysis and incremental embedding job on a small subset (Modules D, E, F).
4. **Expose a basic admin endpoint + minimal UI** for:
   - listing staged imports,
   - viewing textual diffs (even text only).

Once that works for one standard end-to-end (even in a very rough form), we can refine and scale to other standards and broaden the UI and operational robustness.
