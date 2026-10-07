# Admin / OIE / OWASP agent — Mac handover

Continue the end-to-end validation on your Mac (not the cloud agent). Pull branch `cursor/admin-panel-showcase-ccdd` (PR https://github.com/OWASP/OpenCRE/pull/1135, base `cursor/oie-scheduled-runs-eb24`).

---

## Open questions (answer these before the autonomous E2E loop)

Admin ingest currently defaults to **skipping Module B/C** so local demos without LLM keys don’t hang. That only runs **Module A** (chunks → `harvest_input`). For real CRE linking you must call ingest with `skip_b=false` and `skip_c=false` and have LLM credentials set. That is intentional for the Mac E2E run — not a reason to keep skipping.

1. **config.yaml** — Confirm you mean packaged `repos.yaml` (Admin Config / `application/utils/harvester/repos.yaml`), then `POST /admin/ingest/start` with `packaged: true` (or equivalent after editing yaml)?

2. **Upstream sync location** — Wait for / use CRE upstream sync against **local Docker Postgres on the Mac** (`DEV_DATABASE_URL=postgresql://cre:password@127.0.0.1:5432/cre`)? Assumed yes for this handover.

3. **Golden set** — Full current packaged `repos.yaml`, or a smaller curated list? Which repos if curated?

4. **80% / N1 metric** — Confirm OIE B2 hop-distance (`scripts/oie_owasp_eval/score_b2_hop_distance.py` / B2 reports) after Module C, or a different harness?

5. **Full OWASP GitHub org** — Literally all repos, or capped (`max_repos=N`)? What N?

6. **“Graph changed”** — Success = new CRE `node`/`cre`/`cre_links` after Accept/apply, growth in `harvest_input` only, or both?

7. **400 chat questions** — `application/tests/owasp_agent/fixtures/owasp_agent_synth_v2.jsonl` via `make owasp-agent-synth-eval`, or live `POST /rest/v1/completion` for all 400? Pass bar (e.g. ≥80%)?

8. **Nest** — GitHub-only agent sync OK if no `NEST_API_KEY`, or Nest required first?

9. **LLM keys for B/C** — Which env vars are set on the Mac (`GEMINI_API_KEY` / Vertex / etc.)? Without them, forcing B/C on will fail.

---

## Intended E2E sequence (once questions answered)

1. Ensure CRE **upstream sync** has populated local Postgres (`cre` / `node` non-empty). Explorer works.
2. Edit packaged **`repos.yaml`** for the golden set; start ingest via **API** (`packaged: true`, **`skip_b: false`, `skip_c: false`**).
3. Monitor Admin **Pipeline** / import run events until success; fix and retry in a loop if not.
4. Score golden mappings: **N1 neighborhood / ≥80%** (confirm harness in Q4).
5. Expand yaml to **OWASP GitHub org** (per Q5); run another ingest with B/C on.
6. Verify **graph changed** (per Q6); re-check ~80% accuracy.
7. Run **OWASP agent** eval / chat for the ~400 synth questions (per Q7–Q8).
8. Stop and report if graph does not change after the org-wide import.

---

## Mac: branch and run (no upstream re-pull)

```bash
cd ~/Projects/openCRE   # or your clone path
git fetch origin cursor/admin-panel-showcase-ccdd
git checkout cursor/admin-panel-showcase-ccdd
git pull origin cursor/admin-panel-showcase-ccdd

# First time / deps (venv: python3 -m venv fallback if virtualenv missing)
make install

# Reuse existing Postgres + CRE graph — do NOT re-run upstream sync
SKIP_UPSTREAM_SYNC=1 PORT=5001 make dev
```

- Admin: http://127.0.0.1:5001/admin  
- Config (bootstrap buttons + `repos.yaml`): http://127.0.0.1:5001/admin → **Config**  
- Pipeline logs: **Pipeline**  
- Explorer: http://127.0.0.1:5001/explorer  

Port **5000** is often taken by macOS AirPlay — use **5001**.

Force upstream only if graph empty: `FORCE_UPSTREAM_SYNC=1 PORT=5001 make dev` (slow).

Optional CLI:

```bash
# CRE graph only
DEV_DATABASE_URL=postgresql://cre:password@127.0.0.1:5432/cre \
  python cre.py --upstream_sync --cache_file "$DEV_DATABASE_URL"

# Agent sync (Nest skipped without NEST_API_KEY)
make owasp-agent-sync
# or OWASP_AGENT_SYNC_ARGS='--skip-nest --auto-concepts' make owasp-agent-sync
```

---

## Useful API calls (user-equivalent)

Assume `ORIGIN=http://127.0.0.1:5001` and `CRE_ALLOW_IMPORT=1` / `NO_LOGIN=1` (set by `make dev`).

```bash
# Status
curl -s "$ORIGIN/rest/v1/root_cres" | head -c 200
curl -s "$ORIGIN/rest/v1/standards"
curl -s "$ORIGIN/admin/agent/status"
curl -s "$ORIGIN/admin/pipeline"

# Golden / packaged harvest — FULL pipeline (do not skip B/C for E2E)
curl -s -X POST "$ORIGIN/admin/ingest/start" \
  -H 'Content-Type: application/json' \
  -d '{"packaged":true,"skip_b":false,"skip_c":false,"sync_repos":true}'

# OWASP agent sync (Config button → same endpoint)
curl -s -X POST "$ORIGIN/admin/agent/sync" \
  -H 'Content-Type: application/json' \
  -d '{"auto_concepts":true}'

# Monitor
curl -s "$ORIGIN/admin/pipeline" | python3 -m json.tool | less
```

Edit packaged yaml: Admin → Config textarea, **Save repos.yaml**, or edit `application/utils/harvester/repos.yaml` then restart / save via API `PUT /admin/repos.yaml`.

Expand OWASP org into yaml (then save + ingest):

```bash
curl -s -X POST "$ORIGIN/admin/repos.yaml/expand-org" \
  -H 'Content-Type: application/json' \
  -d "{\"yaml\":$(python3 -c 'import json,pathlib; print(json.dumps(pathlib.Path("application/utils/harvester/repos.yaml").read_text()))'),\"owner\":\"OWASP\",\"cron\":\"0 2 * * *\"}"
# then PUT /admin/repos.yaml with returned yaml, then ingest/start
```

---

## What already landed on this branch

| Area | Behavior |
|------|----------|
| `make install` | venv (`python3 -m venv` fallback), Docker Postgres, migrate, `--upstream_sync` if `cre`/`node` empty |
| `make dev` / `dev-flask` / `admin-local` | Same `scripts/run_admin_local.sh` |
| `SKIP_UPSTREAM_SYNC=1` | Skip CRE pull when relaunching |
| Admin → Config | **Run golden-set harvest** + **Sync OWASP agent** |
| `POST /admin/agent/sync` | Nest/GitHub → agent index; Pipeline events `owasp-agent-sync` |
| Admin ingest default | Still **skip B/C** unless client passes `skip_b`/`skip_c` false — **override for E2E** |
| Graph Accept | JSON errors; empty OIE changeset notice (harvest ≠ CRE import ops) |
| OIE observability | skip reasons, flags, graph_path in Pipeline logs |

---

## DB reality check (cloud agent last known)

After upstream sync on cloud Docker Postgres (your Mac may differ):

- ~522 CREs, ~2841 nodes, ~24 standards, `harvest_input` from prior golden harvests  
- Explorer non-empty after upstream; OIE Accept alone does **not** fill Explorer  

On Mac, verify:

```bash
psql postgresql://cre:password@127.0.0.1:5432/cre \
  -c 'select (select count(*) from cre) as cre, (select count(*) from node) as node, (select count(*) from harvest_input) as harvest;'
```

---

## Why B/C skip exists (context only)

Local showcase without LLM keys: B/C timed out → admin defaulted to skip so Module A still demoed. **Point of full ingestion** is A→B→C into knowledge queue / CRE mapping. For this handover’s accuracy goals, **always disable the skip**.

---

## PR / stack

- Branch: `cursor/admin-panel-showcase-ccdd`  
- PR: https://github.com/OWASP/OpenCRE/pull/1135  
- Stack tip base: `cursor/oie-scheduled-runs-eb24` (#1132) — merge whole stack later, not admin alone onto `main`  
- Do not merge to main until Spyros says so  

---

## Suggested first commands after answering questions

```bash
SKIP_UPSTREAM_SYNC=1 PORT=5001 make dev
# Confirm explorer + /rest/v1/standards non-empty
# Set GEMINI_API_KEY (or whatever Module B/C needs)
# POST ingest with skip_b/skip_c false for golden set
# Watch Pipeline until ok; then hop-distance / B2 ≥80%
# Expand OWASP org → ingest → graph delta → agent synth-eval
```

Fill answers to **Open questions** at the top of this file (or paste into chat) before starting the autonomous fix-until-green loop.
