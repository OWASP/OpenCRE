# Admin panel APIs

UI: `/admin`. All routes require **login** and **`CRE_ALLOW_IMPORT`** (`@login_required` + `@imports_enabled`). Anonymous JSON callers get **401**.

## Shell

| Tab | Role |
|-----|------|
| Overview | KPIs, needs-attention, review pulse, agent shortcut |
| Config values | Process env catalog, env vs `.env` diff, bootstrap / `repos.yaml` |
| Pipeline | Job logs and ingest start |
| OIE queue | RQ / OIE worker status |
| Review | Staged links (paginated, collapsible title/content) |
| Workbench | Accepted targets + re-ingest |
| MyOpenCRE / Profile | App shortcuts |

## Notable endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/admin/dashboard` | Includes `needs_attention` and `review_pulse` (accept/adjust/reject from staged decisions — not B2 gold) |
| GET | `/admin/config` | Allowlisted catalog (secrets redacted) |
| GET | `/admin/config/diff` | Compare process env to on-disk `.env` (`match` / `diff` / `missing` / `process_only`) |
| PUT | `/admin/config` | Writable keys only (e.g. `OIE_GRAPH_FILING_ENABLED`) |
| GET | `/admin/imports/runs/<id>/links?page=&page_size=` | Paginated review rows; each `added` includes `title` and `content` |
| GET | `/admin/targets` | Workbench target list |

Browse links for the public site stay in the main header; admin uses a left sidebar.
