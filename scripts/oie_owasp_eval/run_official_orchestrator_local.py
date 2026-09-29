#!/usr/bin/env python3
"""TEMP local helper: drive A→B→C via the official ``run_oie_pipeline``.

Not production. Isolates a copy of ``standards_cache.sqlite`` (CRE hub),
optionally harvests a tiny ASVS slice, then runs Modules B and C through
``application.utils.oie_orchestrator.run_oie_pipeline`` — the same entry
``scripts/run_oie_pipeline.py`` / ``make oie-pipeline`` use.

A backends
  git      — real ``run_harvester`` (needs git clone; Cursor sandbox often blocks)
  tarball  — injects a tarball harvester that still hands off via ``harvest_input``
             (default; works when ``.git`` writes are forbidden)

Examples
  # Small end-to-end (recommended first run)
  PYTHONPATH=. python scripts/oie_owasp_eval/run_official_orchestrator_local.py \\
      --a-mode tarball --max-chunks 20

  # True Module A (Terminal.app / outside sandbox)
  PYTHONPATH=. python scripts/oie_owasp_eval/run_official_orchestrator_local.py \\
      --a-mode git

  # Re-run B+C only against an existing DB + run_id
  PYTHONPATH=. python scripts/oie_owasp_eval/run_official_orchestrator_local.py \\
      --skip-a --db tmp/oie_owasp_eval/orchestrator_full.sqlite --run-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"
DEFAULT_DB = ART / "orchestrator_full.sqlite"
DEFAULT_REPOS_YAML = ART / "orchestrator_repos.yaml"
TARBALL_CACHE = ART / "tarballs"


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _now_run_id() -> str:
    return "orch-local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def _write_tiny_repos_yaml(path: Path) -> None:
    """One ASVS include so git-mode A stays cheap."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
repositories:
  - id: owasp-asvs-local-slice
    type: github
    enabled: true
    owner: OWASP
    repo: ASVS
    branch: master
    paths:
      include:
        - "4.0/en/0x11-V2-Authentication.md"
      exclude:
        - "**/archive/**"
    chunking:
      strategy: markdown_heading
      max_tokens: 1200
      overlap_tokens: 100
    polling:
      mode: incremental
      interval_minutes: 60
"""
    )


def _preflight(*, need_cross_encoder: bool) -> List[str]:
    problems: List[str] = []
    if not (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LLM_API_KEY")
    ):
        problems.append(
            "No embedding/LLM key in env (need GEMINI_API_KEY or OPENAI_API_KEY "
            "for Module B classify + Module C query embeddings)."
        )
    if need_cross_encoder:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            problems.append(
                "sentence-transformers missing — Module C's real C.2 CrossEncoder "
                "will fail. Install with: pip install 'sentence-transformers>=5,<6' "
                "(see requirements-dev.txt; intentionally not on prod requirements)."
            )
    return problems


def _prepare_db(*, src: Path, dst: Path, reuse: bool) -> str:
    if not src.is_file():
        raise SystemExit(f"CRE hub sqlite not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and reuse:
        print(f"reusing DB {dst}", flush=True)
    else:
        print(f"copy {src} → {dst} …", flush=True)
        shutil.copy2(src, dst)
    return _sqlite_url(dst)


def _download_asvs_tarball() -> Path:
    TARBALL_CACHE.mkdir(parents=True, exist_ok=True)
    dest = TARBALL_CACHE / "ASVS.tgz"
    if dest.is_file() and dest.stat().st_size > 1000:
        try:
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return dest
        except Exception:
            dest.unlink(missing_ok=True)
    url = "https://codeload.github.com/OWASP/ASVS/tar.gz/refs/heads/master"
    print(f"GET {url}", flush=True)
    urllib.request.urlretrieve(url, dest)
    return dest


def _tarball_harvester(
    session: Any,
    pipeline_run_id: str,
    *,
    dry_run: bool = False,
    sync_repos: bool = True,  # unused; signature matches run_harvester
    max_chunks: int = 20,
    include_suffix: str = "4.0/en/0x11-V2-Authentication.md",
) -> Any:
    """Injected Module A: same harvest_input contract, no git."""
    from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.heading_extractor import HeadingExtractor
    from application.utils.harvester.models import Document, Locator, SourceInfo
    from application.utils.harvester.pipeline import RunSummary
    from application.utils.harvester.schemas import ChunkingConfig

    tgz = _download_asvs_tarball()
    files: List[Tuple[str, str]] = []
    with tarfile.open(tgz, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            rel = str(Path(*parts[1:]))
            if not rel.endswith(include_suffix) and include_suffix not in rel:
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            text = extracted.read().decode("utf-8", errors="replace")
            if len(text.strip()) < 40:
                continue
            files.append((rel, text))

    chunking = ChunkingConfig(
        strategy="markdown_heading", max_tokens=1200, overlap_tokens=100
    )
    pipeline = DocumentChunkPipeline(chunking=chunking)
    headings = HeadingExtractor()
    committed_at = datetime.now(timezone.utc)
    sha = "tarball00000000000000000000000000000001"
    records = []
    for rel, text in files:
        doc = Document(
            schema_version="0.2.0",
            artifact_id=f"art:OWASP/ASVS:{rel}",
            pipeline_run_id=pipeline_run_id,
            text=text,
            heading_structure=headings.extract(text),
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha=sha,
                committed_at=committed_at,
            ),
            locator=Locator(kind="repo_path", id=rel, path=rel),
        )
        records.extend(pipeline.chunk(doc))

    if max_chunks > 0:
        records = records[:max_chunks]

    summary = RunSummary(
        run_id=pipeline_run_id,
        repositories=1 if files else 0,
        files_seen=len(files),
        files_retained=len(files),
        documents_emitted=len(files),
        dry_run=dry_run,
    )
    if dry_run:
        summary.chunks_written = len(records)
        summary.status = "ok"
        return summary

    written = write_harvest_input(session, pipeline_run_id, records)
    summary.chunks_written = written
    summary.status = "ok" if written else "degraded: no chunks"
    print(
        f"tarball A: files={len(files)} chunks_capped={len(records)} "
        f"written={written}",
        flush=True,
    )
    return summary


def _queue_snapshot(session: Any, run_id: str) -> dict:
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )

    harvest = session.query(HarvestInput).filter_by(pipeline_run_id=run_id).count()
    knowledge = (
        session.query(KnowledgeQueueItem).filter_by(pipeline_run_id=run_id).count()
    )
    knowledge_consumed = (
        session.query(KnowledgeQueueItem)
        .filter(
            KnowledgeQueueItem.pipeline_run_id == run_id,
            KnowledgeQueueItem.consumed_at.isnot(None),
        )
        .count()
    )
    decisions = session.query(DecisionQueueItem).filter_by(pipeline_run_id=run_id).all()
    linked = sum(1 for d in decisions if d.status == "linked")
    review = sum(1 for d in decisions if d.status == "review_required")
    top = sorted(
        (
            {
                "chunk_id": d.chunk_id,
                "status": d.status,
                "reason_code": d.reason_code,
                "confidence": d.confidence,
            }
            for d in decisions
        ),
        key=lambda x: -(x["confidence"] or 0),
    )[:15]
    return {
        "harvest_input": harvest,
        "knowledge_queue": knowledge,
        "knowledge_consumed": knowledge_consumed,
        "decision_queue": len(decisions),
        "linked": linked,
        "review_required": review,
        "top_decisions": top,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="TEMP: official OIE orchestrator A→B→C on a local sqlite copy"
    )
    parser.add_argument(
        "--hub-db",
        type=Path,
        default=ROOT / "standards_cache.sqlite",
        help="source sqlite with CRE embeddings (copied unless --reuse-db / --cache-file)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="destination sqlite path when not using --cache-file",
    )
    parser.add_argument(
        "--cache-file",
        default="",
        help="SQLAlchemy URL (e.g. postgresql://cre:password@127.0.0.1:5432/cre). "
        "When set, skips sqlite hub copy.",
    )
    parser.add_argument("--reuse-db", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--a-mode",
        choices=("tarball", "git"),
        default="tarball",
        help="Module A backend (default tarball for sandbox)",
    )
    parser.add_argument("--skip-a", action="store_true")
    parser.add_argument("--skip-b", action="store_true")
    parser.add_argument("--skip-c", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-sync-repos",
        action="store_true",
        help="git mode: skip clone/fetch (use HARVESTER_CACHE_DIR as-is)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=20,
        help="tarball A only: cap harvest_input rows (0 = no cap)",
    )
    parser.add_argument(
        "--repos-yaml",
        type=Path,
        default=DEFAULT_REPOS_YAML,
        help="git mode: repos.yaml (default: tiny ASVS slice under tmp/)",
    )
    parser.add_argument(
        "--allow-missing-cross-encoder",
        action="store_true",
        help="skip sentence-transformers preflight (C will error at build_components)",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("CRE_LIBRARIAN_RETRIEVER_BACKEND", "in_memory")
    _load_dotenv()

    problems = _preflight(need_cross_encoder=not args.allow_missing_cross_encoder)
    if problems and not args.skip_c:
        print("PREFLIGHT FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    if args.cache_file.strip():
        cache_file = args.cache_file.strip()
        print(f"using cache_file={cache_file}", flush=True)
        db_label = cache_file
    else:
        cache_file = _prepare_db(src=args.hub_db, dst=args.db, reuse=args.reuse_db)
        db_label = str(args.db.resolve())
    run_id = (args.run_id or "").strip() or _now_run_id()

    run_harvester_fn = None
    if not args.skip_a:
        if args.a_mode == "tarball":

            def run_harvester_fn(session, rid, *, dry_run=False, sync_repos=True):
                return _tarball_harvester(
                    session,
                    rid,
                    dry_run=dry_run,
                    sync_repos=sync_repos,
                    max_chunks=args.max_chunks,
                )

        else:
            _write_tiny_repos_yaml(args.repos_yaml)
            from application.utils.harvester.pipeline import run_harvester

            repos_yaml = args.repos_yaml

            def run_harvester_fn(session, rid, *, dry_run=False, sync_repos=True):
                return run_harvester(
                    session,
                    rid,
                    repos_yaml=repos_yaml,
                    dry_run=dry_run,
                    sync_repos=sync_repos,
                )

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.utils.oie_orchestrator import run_oie_pipeline

    print(
        json.dumps(
            {
                "run_id": run_id,
                "cache_file": cache_file,
                "a_mode": "skipped" if args.skip_a else args.a_mode,
                "orchestrator": "application.utils.oie_orchestrator.run_oie_pipeline",
            },
            indent=2,
        ),
        flush=True,
    )

    result = run_oie_pipeline(
        cache_file=cache_file,
        pipeline_run_id=run_id,
        skip_a=args.skip_a,
        skip_b=args.skip_b,
        skip_c=args.skip_c,
        dry_run=args.dry_run,
        sync_repos=not args.no_sync_repos,
        stop_on_error=True,
        run_harvester_fn=run_harvester_fn,
    )

    db_connect(cache_file)
    snap = _queue_snapshot(sqla.session, run_id)
    out = {
        "orchestrator": json.loads(result.to_json()),
        "queues": snap,
        "db": db_label,
        "fix": (
            "Fit CRE_LIBRARIAN_TEMPERATURE via "
            "scripts/evaluate_librarian.py --use_live_embeddings "
            "before trusting auto-links; τ=0.8 assumes calibrated C.2 logits."
        ),
    }
    report_path = ART / f"orchestrator_full_{run_id}.json"
    report_path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"wrote {report_path}", flush=True)
    return 0 if result.to_dict()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
