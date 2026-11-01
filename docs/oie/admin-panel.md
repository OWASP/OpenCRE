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

## Reviewing OIE decisions over REST

Pipeline tab, "OIE decisions", is read-write. The same endpoints work with curl (admin session or API key plus `X-CSRF-Token` on POST; `NO_LOGIN=1` skips both for local testing):

```bash
B=http://127.0.0.1:5000; H='Content-Type: application/json'
curl "$B/admin/oie/cres/search?q=session"                       # find CREs by name or id
curl "$B/admin/oie/decisions?status=review_required"            # queue, with proposed CREs
curl -H "$H" -X POST "$B/admin/oie/decisions/<id>" \
  -d '{"action":"approve"}'                                      # or reject / repoint
curl -H "$H" -X POST "$B/admin/oie/decisions/<id>" \
  -d '{"action":"repoint","cre_ids":["222-222"],"standard_name":"SLSA"}'
curl "$B/admin/oie/filed"                                        # auto-filed / reviewed nodes
curl -H "$H" -X POST "$B/admin/oie/filed/<node_id>/repoint" \
  -d '{"from_cre_id":"111-111","to_cre_id":"333-333","note":"wrong topic"}'
```

- Repo sources file under `OWASP/<repo>`; website and feed sources file under the site's host. Pass `standard_name` to override.
- Reviewer-set links are `Linked To`. Reviewing swaps only the `oie-auto-filed` tag for `oie-reviewed`; other tags stay.
- Every action appends a `decision_review` row (proposal, choice, reviewer, note).
