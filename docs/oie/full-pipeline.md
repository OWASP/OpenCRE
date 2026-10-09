# Full pipeline (repo URL → A → B → C)

End-to-end evaluation for the four agreed families:

| Family | Module A source | Gold |
|--------|-----------------|------|
| ASVS | GitHub `OWASP/ASVS` (`5.0/en`) | `owasp_asvs_5_0_provisional` |
| AISVS | GitHub `OWASP/AISVS` (`1.0/en`) | `owasp_aisvs_1_0` |
| Cheat Sheets | GitHub `OWASP/CheatSheetSeries` | `owasp_cheatsheets_supplement` |
| AI Exchange (AIX) | *Not* GitHub — hub / site CSV | `owasp_llm_top10_2025` (hub AI CREs; #1124) |
| NIST 800-53 v5 | OSCAL prose (`b2_sources/nist_800_53_v5`) | `nist_800_53_v5` (hub Links) |
| Top 10 2025 | Cached hyperlink text | `owasp_top10_2025` |
| API Top 10 2023 | Cached hyperlink text | `owasp_api_top10_2023` |

Build NIST gold + sources::

```bash
PYTHONPATH=. python scripts/oie_owasp_eval/build_nist_800_53_v5_eval.py --sample 48
# full catalog: omit --sample
```

Example expanded arms::

```bash
PYTHONPATH=. python scripts/oie_owasp_eval/run_full_pipeline.py \
  --repos nist,top10,api --keep-all-knowledge --neighborhood
```

## Command

```bash
export CRE_LIBRARIAN_CRE_SUMMARY=1
export CRE_LIBRARIAN_MARGIN_GAMMA=0.85
export DEV_DATABASE_URL=postgresql://cre:password@127.0.0.1:5432/cre

PYTHONPATH=. python scripts/oie_owasp_eval/run_full_pipeline.py \
  --repos asvs,aisvs,cheatsheets,aix \
  --keep-all-knowledge \
  --neighborhood \
  --wipe-queues
```

`--wipe-queues` deletes **every** row in `harvest_input`, `knowledge_queue` and
`decision_queue` of the target database before the GitHub arms run
(`knowledge_queue.content_hash` is globally unique, so stale rows would hide new
output). The script refuses to run those arms without it; point `--cache_file` at
a disposable database.

Harvest uses GitHub **tarballs** (no `.git`). Promoted librarian flags default on.
Reports land under `tmp/oie_owasp_eval/experiments/full_pipeline_*.b2_report.json`
and `tmp/oie_owasp_eval/full_pipeline/summary.json`.

Production Module A list (`application/utils/harvester/repos.yaml`) includes
ASVS 4+5, AISVS, and CheatSheetSeries for live `make oie-pipeline` runs.

## RQ fan-out (optional)

Default `scripts/run_oie_pipeline.py` stays serial (LangGraph). For parallel
repos/documents on the **existing import RQ workers**:

```bash
# workers (default 10 on queue ``oie``)
make start-oie-workers
# or: CRE_OIE_WORKER_COUNT=10 bash scripts/import-all.sh  # partitions ga/oie/import
# fewer/more: OIE_WORKER_COUNT=4 make start-oie-workers

CRE_OIE_RQ=1 PYTHONPATH=. python scripts/run_oie_pipeline.py \
  --run_id my-run --cache_file "$DEV_DATABASE_URL" --repos_yaml path/to/repos.yaml --rq
```

- Queue name: `oie` (`CRE_OIE_QUEUE_NAME`)
- Job units: `oie:a:{repo_id}` → `oie:b:{artifact_id}` → `oie:c:{artifact_id}`
- Default fleet size: **10** (`CRE_OIE_WORKER_COUNT` / `make start-oie-workers`); set `CRE_OIE_WORKER_COUNT=0` to skip OIE slots in import-all
- Admin: **OIE queue** tab polls `/admin/oie/rq/status` (import-dashboard style)
- Do not `--wipe-queues` while another OIE RQ batch shares the DB

## Optional requirement extract

ASVS/AISVS gold is requirement-grain (`V1.1.2`), not chapter. Heading/docling
chunks alone under-harvest exact match. Optional extractor:

| `chunking.requirement_extract` | Behavior |
|--------------------------------|----------|
| `auto` (default if omitted) | Extract only when `requirements_needed(text)` (tables / dense catalogs) |
| `on` | Always attempt extract; fall back to normal chunking if none found |
| `off` | Normal chunk + A.2 merge only |

When extract yields segments, each chunk is prefixed with `Section-ID: V…`
(B2-style) and A.2 merge is skipped. Narrative cheat sheets usually no-op
under `auto`. All repos in `repos.yaml` set `requirement_extract: auto`
explicitly; code defaults to `auto` when the field is missing.
