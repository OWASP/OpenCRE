---
name: review-brevity
description: Launch Brevity bot on the current diff after Bugbot and Security.
---

# Review Brevity

When asked to run `/review-brevity` or Brevity bot:

Launch **three** independent `generalPurpose` subagents (`run_in_background: false`)
with the contents of `.cursor/skills/brevity-bot/SKILL.md` as instructions.

Prompt each with:

```text
Full Repository Path: <absolute repository path>
Diff: branch changes
```

Default to `branch changes`. Use `uncommitted changes` only if asked.

Collect the three `VERDICT:` lines. Majority `NO_COMMENTS` (2 of 3) is clean.
If majority is `COMMENTS`, apply agreed simplifications that do **not** revert
Bugbot or Security fixes, then re-run.
