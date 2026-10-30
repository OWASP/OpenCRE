# `max_repos` on the admin ingest endpoints

`POST /admin/ingest/start` (and the OIE run helpers behind it) accept an optional `max_repos`:

| Value | Meaning |
|---|---|
| omitted / `null` | the capped default (`DEFAULT_OIE_MAX_REPOS`) |
| `N` > 0 | harvest at most N repos |
| `0` | **no cap**: every repo in the selected target |
| negative / not an integer | HTTP 400 |

Why `0` means "unlimited" and not "reject": a full-organisation harvest is a legitimate, deliberate
operation (see `test_ingest_skip_c1_and_unlimited_max_repos`), and it needs an explicit value so it
can never happen by leaving the field out. The default stays capped so an accidental call is cheap.

Implementation: `admin_panel_routes.py` validates (`>= 0`), `service.py` only passes `--max-repos`
to the harvester when the value is `> 0`.
