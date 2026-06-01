#!/usr/bin/env python3
"""Interactive labeling TUI for Module B candidate records (Module A actual shape).

Reads:  application/tests/noise_filter/fixtures/candidate_commits.json
Writes: application/tests/noise_filter/fixtures/labeled_data.json

Records are in Module A's actual emission shape: nested `source` / `span` /
`locator`. Resume key is `chunk_id` (Module A's stable identifier).

Keys (lowercase):
    k = KNOWLEDGE   (introduces a NEW vulnerability, attack vector, testing
                     methodology, bypass technique, or mitigation strategy)
    n = NOISE       (clarification, expanded explanation, additional example,
                     link/tool reference, restructuring, rewording, typo)
    u = UNCERTAIN   (genuinely ambiguous; judgment call could go either way)
    s = SKIP        (drop this record from the dataset entirely)
    ? = re-print the current record (in case you scrolled away)
    q = save and quit

Run from repo root:
    python scripts/label_dataset.py
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

CANDIDATES_PATH = Path("application/tests/noise_filter/fixtures/candidate_commits.json")
LABELED_PATH = Path("application/tests/noise_filter/fixtures/labeled_data.json")
CHUNK_DISPLAY_CHARS = 1200

KEY_TO_LABEL: dict[str, str] = {
    "k": "KNOWLEDGE",
    "n": "NOISE",
    "u": "UNCERTAIN",
}

DEFINITION = """\
================================================================================
DEFINITION (recall-first, agreed with maintainer 2026-06-01):

  KNOWLEDGE = ANY content with a security signal -- vulnerabilities, attack
              vectors, testing methodology, mitigations, code samples,
              advisories, configurations, EVEN clarifications, typo fixes,
              expanded examples, restatements of well-known material, link
              additions, restructured security sections.
              WHEN IN DOUBT, LABEL KNOWLEDGE.

  NOISE     = ONLY content with NO security signal at all -- sponsorship
              pages, meeting notes, CI/build config, release tags, website
              layouts, contributor onboarding, project governance.

  UNCERTAIN = reserved for genuinely 50/50 chunks even after the recall-first
              bias (e.g. half security context, half organizational content).
              Use sparingly.

Rationale: recall > precision. NOISE rows are dropped before Module C, so
mislabeling a security chunk as NOISE means the CRE graph never sees it. False
positives at Stage 2 just waste downstream compute -- Module C re-judges via
its cross-encoder; Module D's HITL can correct. Cost asymmetry strongly favors
keeping borderline cases as KNOWLEDGE.
================================================================================
"""


def load_labeled() -> dict[str, dict[str, Any]]:
    """Indexed by chunk_id (Module A's stable identifier)."""
    if not LABELED_PATH.exists():
        return {}
    raw = json.loads(LABELED_PATH.read_text())
    return {r["chunk_id"]: r for r in raw}


def save_labeled(labeled: dict[str, dict[str, Any]]) -> None:
    LABELED_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LABELED_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(list(labeled.values()), indent=2, ensure_ascii=False))
    os.replace(tmp, LABELED_PATH)


def github_url(repo: str, sha: str) -> str:
    return f"https://github.com/{repo}/commit/{sha}"


def print_record(rec: dict[str, Any], idx: int, total: int) -> None:
    src = rec["source"]
    span = rec["span"]
    loc = rec["locator"]
    print("\n" + "=" * 78)
    print(f"[{idx}/{total}]  chunk_id={rec['chunk_id']}")
    print(f"  artifact_id:    {rec['artifact_id']}")
    print(f"  pipeline_run:   {rec['pipeline_run_id']}")
    print(f"  source_type:    {src['type']}")
    if src["type"] == "github":
        print(f"  repo:           {src['repo']}")
        print(f"  commit_sha:     {src['commit_sha']}")
        print(f"  committed_at:   {src.get('committed_at', '-')}")
        print(f"  url:            {github_url(src['repo'], src['commit_sha'])}")
    elif src["type"] == "rss":
        print(f"  feed_url:       {src.get('feed_url', '-')}")
        print(f"  post_guid:      {src.get('post_guid', '-')}")
        print(f"  published_at:   {src.get('post_published_at', '-')}")
    print(f"  locator:        kind={loc['kind']}  path={loc['path']}")
    print(f"  span:           index={span['index']}/{span['total']}  "
          f"lines={span.get('start_line', '-')}-{span.get('end_line', '-')}")
    print(f"  heading_path:   {' > '.join(span.get('heading_path', []) or ['(root)'])}")
    chunk = rec["text"]
    print(f"  -- text ({len(chunk)} chars total, showing first {CHUNK_DISPLAY_CHARS}) --")
    if len(chunk) > CHUNK_DISPLAY_CHARS:
        print(chunk[:CHUNK_DISPLAY_CHARS])
        print(f"  ... [truncated; {len(chunk) - CHUNK_DISPLAY_CHARS} more chars]")
    else:
        print(chunk)
    print("=" * 78)


def print_progress(labeled: dict[str, dict[str, Any]], total: int) -> None:
    counts = Counter(r["label"] for r in labeled.values())
    print(
        f"  Progress: {len(labeled)}/{total} labeled "
        f"(K={counts.get('KNOWLEDGE', 0)} "
        f"N={counts.get('NOISE', 0)} "
        f"U={counts.get('UNCERTAIN', 0)})"
    )


def main() -> None:
    if not CANDIDATES_PATH.exists():
        sys.exit(
            f"{CANDIDATES_PATH} not found.\n"
            f"Run: python scripts/build_labeled_dataset.py first."
        )

    candidates = json.loads(CANDIDATES_PATH.read_text())
    if candidates and "chunk_id" not in candidates[0]:
        sys.exit(
            f"{CANDIDATES_PATH} is in a legacy shape (no chunk_id). "
            f"Delete it and re-run scripts/build_labeled_dataset.py to "
            f"regenerate in Module A's actual shape."
        )

    labeled = load_labeled()
    me = os.environ.get("USER") or getpass.getuser()
    today = date.today().isoformat()

    pending = [c for c in candidates if c["chunk_id"] not in labeled]

    print(DEFINITION)
    print(f"Total candidates: {len(candidates)}")
    print(f"Already labeled:  {len(labeled)}")
    print(f"Pending:          {len(pending)}")
    print(f"Labeler:          {me} ({today})")

    if not pending:
        print("\nAll candidates have been labeled.")
        print_progress(labeled, len(candidates))
        return

    print("\nKeys: [k]nowledge  [n]oise  [u]ncertain  [s]kip  [?] re-show  [q]uit")

    for rec in pending:
        print_record(rec, len(labeled) + 1, len(candidates))
        while True:
            try:
                ans = input("label> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                save_labeled(labeled)
                print("\n\n(saved progress) Re-run to continue.")
                print_progress(labeled, len(candidates))
                return

            if ans == "q":
                save_labeled(labeled)
                print_progress(labeled, len(candidates))
                print("\nSaved. Re-run to continue.")
                return
            if ans == "?":
                print_record(rec, len(labeled) + 1, len(candidates))
                continue
            if ans == "s":
                print("  skipped (will not be saved)")
                break
            if ans in KEY_TO_LABEL:
                label = KEY_TO_LABEL[ans]
                try:
                    rationale = input("rationale (Enter to skip)> ").strip()
                except (EOFError, KeyboardInterrupt):
                    rationale = ""
                labeled[rec["chunk_id"]] = {
                    **rec,
                    "label": label,
                    "label_rationale": rationale,
                    "labeled_by": me,
                    "labeled_at": today,
                }
                save_labeled(labeled)
                print(f"  -> {label}")
                print_progress(labeled, len(candidates))
                break
            print(f"  unknown key: {ans!r}. Use k/n/u/s/?/q")

    print("\nAll pending records labeled.")
    print_progress(labeled, len(candidates))


if __name__ == "__main__":
    main()
