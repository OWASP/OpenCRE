# Module A — Harvester runbook

**Audience:** operators / OIE orchestrator. **Status:** v1 (2026-08-29).

Module A is a **stateless batch step**: the orchestrator invokes it once per
`pipeline_run_id`; it syncs configured OWASP repos, chunks changed markdown,
validates each chunk as a Module B `ChangeRecord`, inserts `harvest_input`
rows (`status=pending`), updates durable `harvester_checkpoint`s, and exits
with a JSON summary.

---

## Invoke

```bash
python cre.py --run_harvester --run_id <pipeline_run_id> --cache_file <db-url>
```

Optional:

- `--harvester_dry_run` — classify path without inserting rows
- `--harvester_repos_yaml PATH` — override `application/utils/harvester/repos.yaml`

Orchestrated:

```bash
make oie-pipeline OIE_ARGS='--run_id 20260829T020000Z'
# or
python scripts/run_oie_pipeline.py --cache_file <db-url> --run_id <id>
```

---

## Guarantees

- Payload `pipeline_run_id` equals the top-level `harvest_input.pipeline_run_id`.
- Every written payload validates as `application.utils.noise_filter.schemas.ChangeRecord`.
- Chunking follows `repos.yaml` (`markdown_heading` / `fixed_size`); no LlamaIndex on the prod slug.
- Repo-level errors are isolated; a partial run returns `status=degraded` (exit 1).

See also: `blockers.md`, `line-by-line.md`, and
`docs/gsoc_2026_module_b/module_a_contract.md`.
