#!/usr/bin/env python3
"""Wave1 harvest without git: download GitHub tarballs and emit harvest_input.

Used when the agent sandbox forbids writing ``.git/`` (hooks/config). Produces
real ChangeRecord-shaped rows so Module B dual-classify can run.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"

WAVE1: List[Tuple[str, str, List[str]]] = [
    ("ASVS", "master", ["4.0/en/**/*.md", "5.0/en/**/*.md"]),
    ("CheatSheetSeries", "master", ["cheatsheets/**/*.md"]),
    ("wstg", "master", ["document/**/*.md"]),
    ("SAMM", "master", ["**/*.md"]),
    ("Top10", "master", ["**/*.md"]),
    ("API-Security", "master", ["**/*.md"]),
    ("mastg", "master", ["**/*.md"]),
    ("masvs", "master", ["**/*.md"]),
    ("AISVS", "main", ["**/*.md"]),
    (
        "www-project-top-10-for-large-language-model-applications",
        "main",
        ["**/*.md"],
    ),
    ("www-project-proactive-controls", "main", ["**/*.md"]),
    ("www-project-ai-testing-guide", "main", ["**/*.md"]),
    ("www-project-ai-security-and-privacy-guide", "main", ["**/*.md"]),
    ("www-project-devsecops-guideline", "main", ["**/*.md"]),
    ("secure-coding-practices-quick-reference-guide", "master", ["**/*.md"]),
    ("DevSecOpsGuideline", "main", ["**/*.md"]),
    ("MCP-Security-Testing-Guide", "main", ["**/*.md"]),
    ("Software-Component-Verification-Standard", "main", ["**/*.md"]),
    ("IoT-Security-Verification-Standard-ISVS", "master", ["**/*.md"]),
    ("cornucopia", "master", ["**/*.md"]),
]

EXCLUDE = [
    "**/archive/**",
    "**/.github/**",
    "**/node_modules/**",
    "**/LICENSE*",
    "**/CHANGELOG*",
    "**/CONTRIBUTING*",
]


def _match(path: str, patterns: List[str]) -> bool:
    """Glob match with ``**`` support; also try the non-recursive collapse."""
    posix = PurePosixPath(path)
    expanded: List[str] = []
    for pat in patterns:
        expanded.append(pat)
        if "/**/" in pat:
            expanded.append(pat.replace("/**/", "/"))
        if pat.startswith("**/"):
            expanded.append(pat[3:])
    for pat in expanded:
        try:
            if posix.match(pat):
                return True
        except ValueError:
            pass
        if fnmatch.fnmatch(path, pat):
            return True
    return False


def _download_tarball(repo: str, branch: str, dest: Path) -> str:
    """Download tarball; return the branch that worked."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Re-download if truncated/corrupt (small or unreadable)
    if dest.is_file() and dest.stat().st_size > 1000:
        try:
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return branch
        except Exception:
            dest.unlink(missing_ok=True)
    for try_branch in (branch, "main" if branch == "master" else "master"):
        url = f"https://codeload.github.com/OWASP/{repo}/tar.gz/refs/heads/{try_branch}"
        print(f"GET {url}", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return try_branch
        except Exception as exc:  # noqa: BLE001
            print(f"  fail {try_branch}: {exc}", flush=True)
            dest.unlink(missing_ok=True)
    raise RuntimeError(f"could not download tarball for {repo}")


def _iter_md(tgz: Path, includes: List[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    with tarfile.open(tgz, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            rel = str(Path(*parts[1:]))
            if not rel.lower().endswith(".md"):
                continue
            if _match(rel, EXCLUDE):
                continue
            if not _match(rel, includes):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
            if len(text.strip()) < 40:
                continue
            out.append((rel, text))
    return out


def main() -> int:
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    sys.path.insert(0, str(ROOT))

    state = json.loads((ART / "state.json").read_text())
    run_id = state["run_id"] + "-w1"
    db_path = ART / "eval.sqlite"
    if db_path.exists():
        db_path.unlink()
    db_url = f"sqlite:///{db_path}"

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.heading_extractor import HeadingExtractor
    from application.utils.harvester.models import Document, Locator, SourceInfo
    from application.utils.harvester.schemas import ChunkingConfig

    db_connect(db_url)
    sqla.create_all()

    chunking = ChunkingConfig(
        strategy="markdown_heading", max_tokens=1200, overlap_tokens=100
    )
    pipeline = DocumentChunkPipeline(chunking=chunking)
    headings = HeadingExtractor()
    committed_at = datetime.now(timezone.utc)
    sha = "tarball00000000000000000000000000000001"

    by_repo: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    tarball_dir = ART / "tarballs"
    tarball_dir.mkdir(parents=True, exist_ok=True)

    for repo, branch, includes in WAVE1:
        try:
            tgz = tarball_dir / f"{repo}.tgz"
            _download_tarball(repo, branch, tgz)
            files = _iter_md(tgz, includes)
            repo_records = []
            for rel, text in files:
                artifact_id = f"art:OWASP/{repo}:{rel}"
                doc = Document(
                    schema_version="0.2.0",
                    artifact_id=artifact_id,
                    pipeline_run_id=run_id,
                    text=text,
                    heading_structure=headings.extract(text),
                    source=SourceInfo(
                        type="github",
                        repository=f"OWASP/{repo}",
                        commit_sha=sha,
                        committed_at=committed_at,
                    ),
                    locator=Locator(kind="repo_path", id=rel, path=rel),
                )
                repo_records.extend(pipeline.chunk(doc))
            written = write_harvest_input(sqla.session, run_id, repo_records)
            by_repo[f"OWASP/{repo}"] = written
            print(f"{repo}: files={len(files)} chunks={written}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors[repo] = str(exc)
            print(f"{repo}: ERROR {exc}", flush=True)

    snap = {
        "run_id": run_id,
        "mode": "tarball",
        "total_rows": sum(by_repo.values()),
        "by_repo": dict(sorted(by_repo.items(), key=lambda kv: -kv[1])),
        "errors": errors,
    }
    (ART / "harvest_wave1_snapshot.json").write_text(json.dumps(snap, indent=2) + "\n")
    (ART / "harvest_wave1.json").write_text(
        json.dumps(
            {
                "exit_code": 0 if by_repo else 1,
                "summary": {
                    "run_id": run_id,
                    "repositories": len(WAVE1),
                    "chunks_written": snap["total_rows"],
                    "errors": len(errors),
                    "status": "ok" if snap["total_rows"] else "degraded",
                    "mode": "tarball",
                },
            },
            indent=2,
        )
        + "\n"
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["wave1_run_id"] = run_id
    state["db_url"] = db_url
    state["phase"] = "classify_dual" if snap["total_rows"] else "harvest_wave1"
    state["status"] = "running" if snap["total_rows"] else "error"
    state["last_error"] = None if snap["total_rows"] else json.dumps(errors)
    state["phases"]["harvest_wave1"] = {
        "status": "ok" if snap["total_rows"] else "error",
        "detail": f"tarball chunks={snap['total_rows']} errors={len(errors)}",
        "at": now,
    }
    state["updated_at"] = now
    (ART / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    (ART / "STATUS.md").write_text(
        f"# OIE OWASP eval status\n\n"
        f"- phase: **{state['phase']}**\n"
        f"- status: **{state['status']}**\n"
        f"- harvest chunks: **{snap['total_rows']}**\n"
        f"- updated: {now}\n"
    )
    print(json.dumps(snap, indent=2))
    return 0 if snap["total_rows"] else 1


if __name__ == "__main__":
    sys.exit(main())
