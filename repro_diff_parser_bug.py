"""Standalone repro for the DiffParser path-handling bugs.

Run with: python repro_diff_parser_bug.py
Requires: git available on PATH, run from inside a venv with the repo's deps.
"""

import subprocess
import tempfile
import os
from datetime import datetime, timezone

from application.utils.harvester.diff_parser import DiffParser


def run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )


def make_repo_with_change(tmpdir, filename, first_content, second_content):
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "test@test.com"], repo)
    run(["git", "config", "user.name", "Test"], repo)

    path = os.path.join(repo, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(first_content)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "initial"], repo)

    with open(path, "w", encoding="utf-8") as f:
        f.write(second_content)
    result = run(["git", "diff"], repo)
    return result.stdout


def main():
    parser = DiffParser()

    print("=" * 70)
    print("BUG A: non-ASCII filename -> diff silently dropped")
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        diff = make_repo_with_change(
            tmpdir, "café.md", "line1\n", "line1\nadded line\n"
        )
        print("--- raw git diff ---")
        print(diff)
        blocks = parser.parse(
            diff,
            repository="test-repo",
            commit_sha="abc123",
            committed_at=datetime.now(timezone.utc),
        )
        print(f"--- DiffParser result: {len(blocks)} block(s) ---")
        for b in blocks:
            print(f"  file_path={b.file_path!r} added_lines={b.added_lines!r}")
        print("EXPECTED: 1 block, file_path='café.md', added_lines=['added line']")
        print(f"BUG CONFIRMED: {len(blocks) == 0}")

    print()
    print("=" * 70)
    print('BUG B: filename containing " b/" -> path truncated')
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        diff = make_repo_with_change(tmpdir, "foo b/bar.md", "x\n", "x\nmore\n")
        print("--- raw git diff ---")
        print(diff)
        blocks = parser.parse(
            diff,
            repository="test-repo",
            commit_sha="abc123",
            committed_at=datetime.now(timezone.utc),
        )
        print(f"--- DiffParser result: {len(blocks)} block(s) ---")
        for b in blocks:
            print(f"  file_path={b.file_path!r} added_lines={b.added_lines!r}")
        print("EXPECTED: file_path='foo b/bar.md'")
        if blocks:
            print(f"BUG CONFIRMED: {blocks[0].file_path != 'foo b/bar.md'}")


if __name__ == "__main__":
    main()
