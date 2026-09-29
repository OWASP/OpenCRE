# Full pipeline (repo URL → A → B → C)

End-to-end evaluation for the four agreed families:

| Family | Module A source | Gold |
|--------|-----------------|------|
| ASVS | GitHub `OWASP/ASVS` (`5.0/en`) | `owasp_asvs_5_0_provisional` |
| AISVS | GitHub `OWASP/AISVS` (`1.0/en`) | `owasp_aisvs_1_0` |
| Cheat Sheets | GitHub `OWASP/CheatSheetSeries` | `owasp_cheatsheets_supplement` |
| AI Exchange (AIX) | *Not* GitHub — hub / site CSV | `owasp_llm_top10_2025` (CRE proxy) |
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
  --neighborhood
```

Or: `make oie-full-pipeline`.

Harvest uses GitHub **tarballs** (no `.git`). Promoted librarian flags default on.
Reports land under `tmp/oie_owasp_eval/experiments/full_pipeline_*.b2_report.json`
and `tmp/oie_owasp_eval/full_pipeline/summary.json`.

Production Module A list (`application/utils/harvester/repos.yaml`) includes
ASVS 4+5, AISVS, and CheatSheetSeries for live `make oie-pipeline` runs.

## Optional requirement extract

ASVS/AISVS gold is requirement-grain (`V1.1.2`), not chapter. Heading/docling
chunks alone under-harvest exact match. Optional extractor:

| `chunking.requirement_extract` | Behavior |
|--------------------------------|----------|
| `off` (default) | Normal chunk + A.2 merge |
| `auto` | Extract only when `requirements_needed(text)` (tables / dense catalogs) |
| `on` | Always attempt extract; fall back to normal chunking if none found |

When extract yields segments, each chunk is prefixed with `Section-ID: V…`
(B2-style) and A.2 merge is skipped. Cheat sheets stay `off` / narrative.
YAML: ASVS + AISVS use `auto` in `repos.yaml` and `full_pipeline_repos.yaml`.
