#!/usr/bin/env python3
"""Harvest candidate OWASP records for Module B labeling (Module A actual shape).

Emits records matching Module A's actual emission shape (mock confirmed
2026-05-29): nested `source` / `span` / `locator`, no `content_hash` field
(Module B computes its own on ingest).

Per the Module A -> Module B input contract:
- Fetches FULL FILE CONTENT at each commit (not diff hunks).
- Applies the v0.2 normalization rules (NFC, line endings, whitespace,
  code-fence preservation) -- see application/utils/noise_filter/hashing.py.
- Chunks via markdown headings at max_chars=4000, tracking heading_path
  and character / line offsets in the normalized artifact text.
- Builds Module A's nested record shape.

Reads GITHUB_TOKEN from environment. Overwrites
application/tests/noise_filter/fixtures/candidate_commits.json on each run.

Run from repo root:
    python scripts/build_labeled_dataset.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from github import Auth, Github, GithubException
except ImportError:
    sys.exit("PyGithub not installed. Run: pip install -r requirements-dev.txt")


# --- Configuration --------------------------------------------------------

SCHEMA_VERSION = "0.2.0"

REPOS_TO_HARVEST = [
    "OWASP/wstg",
    "OWASP/ASVS",
    "OWASP/CheatSheetSeries",
    "OWASP/SAMM",
]

TARGET_RECORDS_PER_REPO = 25
MAX_COMMITS_TO_SCAN_PER_REPO = 30
MAX_FILES_PER_COMMIT = 5
MAX_CHUNK_CHARS = 4000  # Module A contract: chunking.max_chars default

DENY_PATH_PREFIXES = (
    "tests/",
    "test/",
    ".github/",
    "node_modules/",
    "dist/",
    "build/",
    "_layouts/",
    "_includes/",
    "_data/",
    "assets/",
    "docs/_layouts/",
)
DENY_EXTENSIONS = (
    ".css",
    ".scss",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".gif",
    ".lock",
    ".map",
    ".min.js",
    ".min.css",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".yml",
    ".yaml",
    ".json",
)
DENY_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "CNAME",
    "_config.yml",
    ".gitignore",
    ".gitattributes",
    "CODEOWNERS",
    ".editorconfig",
    "mkdocs.yml",
}

OUTPUT_PATH = Path("application/tests/noise_filter/fixtures/candidate_commits.json")


# --- Path filter ----------------------------------------------------------


def is_doc_file(path: str) -> bool:
    if any(path.startswith(p) for p in DENY_PATH_PREFIXES):
        return False
    basename = path.rsplit("/", 1)[-1]
    if basename in DENY_FILENAMES:
        return False
    if any(path.endswith(ext) for ext in DENY_EXTENSIONS):
        return False
    return True


# --- v0.2 normalization (duplicated from hashing.py to keep this script
# standalone -- the script doesn't import from application/) --------------

_FENCE_RE = re.compile(r"```[^\n]*\n.*?\n```|<pre>.*?</pre>", re.DOTALL)
_PROSE_WS_RE = re.compile(r"[ \t]+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    last = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(_process_prose(text[last : m.start()]))
        parts.append(_process_fence(m.group(0)))
        last = m.end()
    if last < len(text):
        parts.append(_process_prose(text[last:]))
    return "".join(parts).strip("\n")


def _process_prose(segment: str) -> str:
    return "\n".join(
        _PROSE_WS_RE.sub(" ", line).rstrip() for line in segment.split("\n")
    )


def _process_fence(segment: str) -> str:
    return "\n".join(line.rstrip() for line in segment.split("\n"))


# --- Position-aware markdown chunker -------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# <pre> open/close tags. Must not match <pre-something> or <preformatted>.
_PRE_OPEN_RE = re.compile(r"<pre[\s>]")
_PRE_CLOSE_RE = re.compile(r"</pre\s*>")


@dataclass
class Chunk:
    """One chunk of normalized artifact text with position metadata."""

    text: str
    start_char_idx: int  # into the normalized artifact text
    end_char_idx: int
    start_line: int  # 1-based line number in the normalized artifact
    end_line: int
    heading_path: list[str]


def chunk_markdown(
    normalized_text: str, max_chars: int = MAX_CHUNK_CHARS
) -> list[Chunk]:
    """Split text into chunks at heading boundaries (fence-aware).

    Tracks heading_path as a stack and char/line offsets into the original
    `normalized_text`. Single-chunk artifacts get a chunk spanning the whole
    document.
    """
    if not normalized_text:
        return []

    lines = normalized_text.split("\n")
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    sections: list[Chunk] = []
    current_lines: list[str] = []
    current_start_line = 1  # 1-based
    current_start_char = 0
    current_heading_path: list[str] = []
    in_fence = False
    pre_depth = 0
    char_cursor = 0

    def flush(end_line_exclusive: int, end_char_exclusive: int) -> None:
        if not current_lines:
            return
        text = "\n".join(current_lines).strip("\n")
        if not text:
            return
        sections.append(
            Chunk(
                text=text,
                start_char_idx=current_start_char,
                end_char_idx=end_char_exclusive,
                start_line=current_start_line,
                end_line=end_line_exclusive - 1,
                heading_path=list(current_heading_path),
            )
        )

    for line_idx, line in enumerate(lines):
        line_no = line_idx + 1  # 1-based
        line_start_char = char_cursor

        # Track fence open/close
        if line.startswith("```"):
            in_fence = not in_fence
            current_lines.append(line)
            char_cursor += len(line) + 1  # +1 for the \n we split on
            continue

        # Track <pre>...</pre> depth. The "was_in_pre" flag captures the state
        # at the START of this line; subsequent count updates apply to lines
        # AFTER this one. This handles the common multi-line <pre> block.
        # A pathological single-line case (`<pre># heading`) is rare and would
        # still be slightly mis-classified -- pragmatic trade-off.
        was_in_pre = pre_depth > 0
        opens_on_line = len(_PRE_OPEN_RE.findall(line))
        closes_on_line = len(_PRE_CLOSE_RE.findall(line))
        pre_depth = max(0, pre_depth + opens_on_line - closes_on_line)

        # Heading? (only outside fences AND outside <pre> blocks)
        m = _HEADING_RE.match(line) if not in_fence and not was_in_pre else None
        if m:
            # Close the previous section before starting this one
            if current_lines:
                flush(
                    end_line_exclusive=line_no, end_char_exclusive=line_start_char - 1
                )
            level = len(m.group(1))
            title = m.group(2).strip()
            # Pop deeper or equal levels, then push
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_heading_path = [t for _, t in heading_stack]
            current_lines = [line]
            current_start_line = line_no
            current_start_char = line_start_char
        else:
            current_lines.append(line)

        char_cursor += len(line) + 1  # account for \n separator

    # Flush the trailing section
    flush(end_line_exclusive=len(lines) + 1, end_char_exclusive=len(normalized_text))

    # Sub-split any oversized sections on paragraph (blank-line) boundaries.
    out: list[Chunk] = []
    for sec in sections:
        if len(sec.text) <= max_chars:
            out.append(sec)
        else:
            out.extend(_split_chunk_by_size(sec, max_chars))
    return out


def _split_chunk_by_size(chunk: Chunk, max_chars: int) -> list[Chunk]:
    """Split a too-large chunk on `\\n\\n` boundaries, preserving metadata.

    Sub-chunks inherit heading_path. char/line offsets are computed with the
    correct separator width per entry:
      * Normal `\\n\\n` boundary -> +2 chars, +2 lines between sub-chunks.
      * Hard-split fragment from an oversized paragraph -> contiguous in the
        original text (0 chars, 0 lines between sub-chunks).
    """
    parts = chunk.text.split("\n\n")
    # Each entry: (text, sep_before_chars). sep_before is 2 for normal
    # paragraph boundaries (preceded by `\n\n`), 0 for hard-split fragments
    # that continue the previous entry's paragraph contiguously.
    entries: list[tuple[str, int]] = []
    buf = ""

    def _flush_buf() -> None:
        """Emit `buf` as a normally-separated entry (preceded by \\n\\n)."""
        nonlocal buf
        if buf:
            sep = 2 if entries else 0  # first entry isn't preceded by anything
            entries.append((buf, sep))
            buf = ""

    for p in parts:
        if len(p) > max_chars:
            _flush_buf()
            for i in range(0, len(p), max_chars):
                piece = p[i : i + max_chars]
                if i == 0:
                    sep = 2 if entries else 0
                else:
                    sep = 0  # contiguous hard-split fragment
                entries.append((piece, sep))
        elif (len(buf) + len(p) + (2 if buf else 0)) <= max_chars:
            buf = (buf + "\n\n" + p) if buf else p
        else:
            _flush_buf()
            buf = p
    _flush_buf()

    # Compute offsets, advancing past each entry's separator before recording.
    # sep is 0 or 2; `\n\n` contains 2 newline chars -> +2 lines, conveniently
    # the same numeric value as the char advance.
    out: list[Chunk] = []
    cursor_char = chunk.start_char_idx
    cursor_line = chunk.start_line
    for text, sep_before in entries:
        cursor_char += sep_before
        cursor_line += sep_before
        end_char = cursor_char + len(text)
        end_line = cursor_line + text.count("\n")
        out.append(
            Chunk(
                text=text,
                start_char_idx=cursor_char,
                end_char_idx=end_char,
                start_line=cursor_line,
                end_line=end_line,
                heading_path=chunk.heading_path,
            )
        )
        cursor_char = end_char
        cursor_line = end_line
    return out


# --- Record building (Module A nested shape) -----------------------------


def make_artifact_id(repo: str, file_path: str) -> str:
    """Format: art:<repo>:<path>"""
    return f"art:{repo}:{file_path}"


def make_chunk_id(artifact_id: str, chunk_index: int) -> str:
    """Format: chk:<artifact_id>:<index>"""
    return f"chk:{artifact_id}:{chunk_index}"


def make_records_for_file(
    repo: str,
    commit_sha: str,
    file_path: str,
    file_content: str,
    committed_at_iso: str,
    pipeline_run_id: str,
) -> list[dict[str, Any]]:
    """Build Module-A-shaped records for one (commit, file) pair."""
    normalized = normalize_text(file_content)
    if not normalized:
        return []

    chunks = chunk_markdown(normalized, max_chars=MAX_CHUNK_CHARS)
    if not chunks:
        return []

    artifact_id = make_artifact_id(repo, file_path)
    total = len(chunks)

    records: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "chunk_id": make_chunk_id(artifact_id, i),
                "artifact_id": artifact_id,
                "pipeline_run_id": pipeline_run_id,
                "text": chunk.text,
                "span": {
                    "index": i,
                    "total": total,
                    "heading_path": chunk.heading_path,
                    "start_char_idx": chunk.start_char_idx,
                    "end_char_idx": chunk.end_char_idx,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                },
                "source": {
                    "type": "github",
                    "repo": repo,
                    "commit_sha": commit_sha,
                    "committed_at": committed_at_iso,
                },
                "locator": {
                    "kind": "repo_path",
                    "id": file_path,
                    "path": file_path,
                },
            }
        )
    return records


# --- Persistence ----------------------------------------------------------


def save_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


# --- Main harvest loop ----------------------------------------------------


def harvest_repo(
    gh: Github,
    repo_name: str,
    pipeline_run_id: str,
    existing_chunk_ids: set[str],
) -> list[dict[str, Any]]:
    print(f"\n=== {repo_name} ===")
    try:
        repo = gh.get_repo(repo_name)
    except GithubException as e:
        print(f"  ERROR fetching repo: {e}")
        return []

    new_records: list[dict[str, Any]] = []
    scanned = 0

    for commit in repo.get_commits():
        if scanned >= MAX_COMMITS_TO_SCAN_PER_REPO:
            print(f"  scanned {scanned} commits, stopping")
            break
        if len(new_records) >= TARGET_RECORDS_PER_REPO:
            break
        scanned += 1

        try:
            files = list(commit.files)[:MAX_FILES_PER_COMMIT]
        except GithubException as e:
            print(f"  ERROR fetching file list for {commit.sha[:7]}: {e}")
            continue

        dt = commit.commit.author.date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        committed_at_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        for f in files:
            if len(new_records) >= TARGET_RECORDS_PER_REPO:
                break
            if f.status == "removed":
                continue
            if not is_doc_file(f.filename):
                continue

            try:
                content_obj = repo.get_contents(f.filename, ref=commit.sha)
            except GithubException as e:
                print(f"  ERROR fetching {f.filename}@{commit.sha[:7]}: {e}")
                continue
            if isinstance(content_obj, list):
                continue
            try:
                raw_text = content_obj.decoded_content.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                continue

            for rec in make_records_for_file(
                repo=repo_name,
                commit_sha=commit.sha,
                file_path=f.filename,
                file_content=raw_text,
                committed_at_iso=committed_at_iso,
                pipeline_run_id=pipeline_run_id,
            ):
                if len(new_records) >= TARGET_RECORDS_PER_REPO:
                    break
                if rec["chunk_id"] in existing_chunk_ids:
                    continue
                new_records.append(rec)
                existing_chunk_ids.add(rec["chunk_id"])
                print(
                    f"  + {commit.sha[:7]} {f.filename} "
                    f"[chunk {rec['span']['index']}/{rec['span']['total']}, "
                    f"heading_path={rec['span']['heading_path']}]"
                )

    print(f"  -> {len(new_records)} new records (scanned {scanned} commits)")
    return new_records


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN not set. Add to .env and re-run.")
    if not Path("application").is_dir():
        sys.exit("Run from repo root (no 'application/' directory here).")

    if OUTPUT_PATH.exists():
        print(
            f"WARNING: {OUTPUT_PATH} exists. Overwriting (Module A shape replaces prior)."
        )
        OUTPUT_PATH.unlink()

    pipeline_run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"pipeline_run_id: {pipeline_run_id}")

    gh = Github(auth=Auth.Token(token), per_page=30)

    try:
        rl = gh.get_rate_limit()
        core = getattr(rl, "core", None) or rl.resources.core
        print(
            f"GitHub rate limit: {core.remaining}/{core.limit} "
            f"(resets {core.reset.isoformat()})"
        )
    except Exception as e:
        print(f"(could not read rate limit: {e})")

    existing_chunk_ids: set[str] = set()
    all_records: list[dict[str, Any]] = []

    for repo_name in REPOS_TO_HARVEST:
        new = harvest_repo(gh, repo_name, pipeline_run_id, existing_chunk_ids)
        all_records.extend(new)
        save_atomic(OUTPUT_PATH, all_records)

    print(f"\nWrote {len(all_records)} total records to {OUTPUT_PATH}")
    print("Distribution by repo:")
    for repo_name in REPOS_TO_HARVEST:
        count = sum(1 for r in all_records if r["source"]["repo"] == repo_name)
        print(f"  {repo_name}: {count}")

    chunk_ids = [r["chunk_id"] for r in all_records]
    dupes = len(chunk_ids) - len(set(chunk_ids))
    if dupes:
        print(f"WARNING: {dupes} duplicate chunk_id values!")
    else:
        print("All chunk_id values unique.")

    print("\nNext step: python scripts/label_dataset.py")


if __name__ == "__main__":
    main()
