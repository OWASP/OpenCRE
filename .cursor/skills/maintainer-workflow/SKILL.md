---
name: maintainer-workflow
description: >-
  Run the OpenCRE maintainer triage workflow: prod GA health, open PR buckets
  (merge-ready / close-ready / needs work), stale issue and PR alerts, GSoC
  checkpoint glance, and one recommended next action for the maintainer.
  Use when asked to run the maintainer skill/workflow, triage the repo, or
  find what needs attention.
---

# OpenCRE Maintainer Workflow

Read-only by default. Only merge/close/comment when the user explicitly asks.

Repo: `OWASP/OpenCRE`. Prefer `gh` with unsandboxed network. Do not switch the
user off an active feature branch unless they ask — use reports only, or a
worktree.

## Steps (run in order)

### 1. Production health
```bash
python3 scripts/monitor_ga_health.py --base-url https://opencre.org --output-json tmp/prod-ga-health.json
python3 scripts/verify_ga_completeness.py --base-url https://opencre.org --output-json tmp/prod-ga-completeness.json
```
Optional smoke: `GET /rest/v1/standards` and `/rest/v1/ga_standards` non-empty.
On Heroku/opencreorg, GA is cache-only — never compute GA on prod.

### 2. Open PR triage (three buckets)
Classify **all** open PRs:

| Bucket | Criteria |
|--------|----------|
| **Ready to merge** | Not draft; mergeable/CLEAN; APPROVED; CI green (ignore perpetual `e2e.yml` noise if other checks pass) |
| **Ready to close** | Stale **>90 days** since last update **and** (conflicts **or** obsolete/superseded/no viable path). One-line reason each. Be conservative. |
| **Need more work** | Everything else — sub-group: review-blocked (esp. CODEOWNERS), CI red, conflicts but recent, changes requested |

Always call out maintainer/P1 PRs if open (slug/requirements, pgvector, etc.).

### 2b. PR comment context (required before merge-ready / deep review)
**Do not skip.** Before marking a PR merge-ready, recommending merge, or doing a deep review of an active PR:

1. Load **all** conversation comments and review threads (`gh api …/issues/{n}/comments`, `…/pulls/{n}/comments`, and `gh pr view --json reviews,comments`).
2. Put that text into the working context — especially comments from **other maintainers** and from **contributors who flag overlap**, prior art, or linked PRs/issues.
3. Explicitly check for: duplicate/overlapping PRs, “already fixed in #…”, design constraints from mentors, and CHANGES_REQUESTED history that contradicts a stale APPROVED state.
4. If an important comment was missed in a prior triage, call it out in the report and adjust the bucket (e.g. APPROVED → need-work / changes-requested).

Lesson: #751 looked merge-ready after rebase until Prateek’s overlap note on #682/#683 + `validate_import_csv_rows` was re-read.

### 2c. Re-review PRs touched since last triage
**Required every run.** Prefer action over leaving stale review state:

1. Identify open non-draft PRs whose `updatedAt` (or new commits / author push) is **newer than the last maintainer review or CHANGES_REQUESTED / approve comment** from us — especially GSoC / active contributor stacks.
2. If prior ask was mechanical (rebase, black, CI green) and the PR is now **MERGEABLE + CI green**, put it in a **“Ready to re-review”** bucket in the report (separate from first-pass review-blocked).
3. When the user asks to act on the queue, **re-review those first** before hunting new PRs — clear CHANGES_REQUESTED or approve/merge as appropriate.
4. Cross-check Slack/author pings (“rebased and green”) against GitHub before trusting them; then deep-review if the claim holds.

### 3. Stale tickets and PRs (alert + track)
**Required every run** — do not skip.

**Stale PRs**
- List open PRs with `updatedAt` older than **90 days**.
- Flag those that are also `DIRTY`/conflicting or have no review activity.
- Summarize counts: stale total, stale+conflict, oldest batch by author if useful.
- Suggest close candidates (link to Ready-to-close bucket); do not close unless asked.

**Stale issues**
- List open issues with `updatedAt` older than **90 days** (limit ~50–100).
- Prefer highlighting: `P1` / `help wanted` / `good first issue`, unassigned with comments, or no linked open PR.
- Note issues that look superseded by shipped work (candidate close-with-comment).

### 4. GSoC / contributor glance (lightweight)
If `scripts/gsoc_pr_review_report.py` exists, run it. Otherwise a short manual table of open GSoC-labeled PRs/issues is enough — do not block the workflow on a missing script.

### 5. Recommend one next action
End with **exactly one** primary recommendation for the maintainer *right now*, in priority order:

1. Merge a merge-ready PR (approved + green)
2. Unblock a P1 PR (review/CI) that gates prod (e.g. Heroku slug)
3. Close a clearly obsolete stale PR/issue batch (only if user wants closes)
4. Otherwise the highest-leverage open `P1` / `help wanted` issue without an active green PR

Format:
```
### Next for maintainer
- **Do:** <action> — <url>
- **Why:** <one sentence>
```

## Output template

```markdown
## Maintainer workflow — YYYY-MM-DD

### Production health
...

### PRs — ready to merge
...

### PRs — ready to re-review
... touched since last maintainer review; prior ask cleared (rebase/CI/etc.) ...

### PRs — ready to close (stale / obsolete)
... counts + short list ...

### PRs — need more work
... grouped ...

### Stale alerts
- Open PRs >90d: N (M conflicting)
- Open issues >90d: N (highlights: ...)

### Next for maintainer
- **Do:** ...
- **Why:** ...
```

## Optional local interactive triage
Gitignored tooling under `project management scripts/` (`SETUP.txt`, `run_interactive.sh`) can walk issues interactively. Requires `.env` + `CURSOR_API_KEY`. Not required for this skill’s report.

## Merge policy reminder
When the user asks to merge: **rebase merge only** (`gh pr merge --rebase`). Never squash/merge-commit unless they override for a one-off.
