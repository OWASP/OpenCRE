#!/usr/bin/env python3
"""Phase A runner: LangGraph orchestrator + Docling chunks for ASVS + CheatSheets.

Tarball harvest (sandbox-safe), Docling chunking, then B→C on local Postgres.
Writes ``tmp/oie_owasp_eval/phase_a_status.json``.
"""

from __future__ import annotations

import json
import os
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"
TARBALLS = ART / "tarballs"

REPOS: List[Tuple[str, str, List[str]]] = [
    (
        "ASVS",
        "master",
        ["4.0/en/0x11-V2-Authentication.md", "4.0/en/0x12-V3-Session-management.md"],
    ),
    (
        "CheatSheetSeries",
        "master",
        [
            "cheatsheets/Authentication_Cheat_Sheet.md",
            "cheatsheets/Password_Storage_Cheat_Sheet.md",
            "cheatsheets/Forgot_Password_Cheat_Sheet.md",
        ],
    ),
]


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


def _download(repo: str, branch: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        try:
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return
        except Exception:
            dest.unlink(missing_ok=True)
    for b in (branch, "main", "master"):
        url = f"https://codeload.github.com/OWASP/{repo}/tar.gz/refs/heads/{b}"
        print(f"GET {url}", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            with tarfile.open(dest, "r:gz") as tf:
                tf.getmembers()[:1]
            return
        except Exception as exc:  # noqa: BLE001
            print(f"  fail {b}: {exc}", flush=True)
            dest.unlink(missing_ok=True)
    raise RuntimeError(f"tarball download failed for {repo}")


def _extract_files(tgz: Path, includes: List[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    with tarfile.open(tgz, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            rel = str(Path(*parts[1:]))
            if not any(rel.endswith(i) or i in rel for i in includes):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            text = extracted.read().decode("utf-8", errors="replace")
            if len(text.strip()) < 40:
                continue
            out.append((rel, text))
    return out


def main() -> int:
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("CRE_LIBRARIAN_RETRIEVER_BACKEND", "pgvector")
    _load_dotenv()
    # Prefer calibrated T from setup_oie
    oie_env = ROOT / "tmp" / "oie.env"
    if oie_env.is_file():
        for line in oie_env.read_text().splitlines():
            if line.startswith("CRE_LIBRARIAN_") or line.startswith("DEV_DATABASE"):
                k, _, v = line.partition("=")
                if k and v:
                    os.environ[k.strip()] = v.strip()

    cache = os.environ.get(
        "DEV_DATABASE_URL", "postgresql://cre:password@127.0.0.1:5432/cre"
    )
    run_id = "orch-docling-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )
    from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.heading_extractor import HeadingExtractor
    from application.utils.harvester.models import Document, Locator, SourceInfo
    from application.utils.harvester.pipeline import RunSummary
    from application.utils.harvester.schemas import ChunkingConfig
    from application.utils.oie_orchestrator import run_oie_pipeline

    headings = HeadingExtractor()
    committed_at = datetime.now(timezone.utc)
    sha = "tarball00000000000000000000000000000002"

    def run_harvester(
        session: Any, rid: str, *, dry_run: bool = False, sync_repos: bool = True
    ):
        summary = RunSummary(run_id=rid, dry_run=dry_run, repositories=0)
        all_records = []
        for repo, branch, includes in REPOS:
            summary.repositories += 1
            profile = "requirements" if repo == "ASVS" else "narrative"
            chunking = ChunkingConfig(
                strategy="docling",
                max_tokens=1200 if repo == "ASVS" else 1000,
                overlap_tokens=100,
                merge_profile=profile,
            )
            pipeline = DocumentChunkPipeline(chunking=chunking)
            tgz = TARBALLS / f"{repo}.tgz"
            _download(repo, branch, tgz)
            files = _extract_files(tgz, includes)
            summary.files_seen += len(files)
            summary.files_retained += len(files)
            for rel, text in files:
                doc = Document(
                    schema_version="0.2.0",
                    artifact_id=f"art:OWASP/{repo}:{rel}",
                    pipeline_run_id=rid,
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
                recs = pipeline.chunk(doc)
                all_records.extend(recs)
                print(
                    f"  {repo}/{rel}: chunks={len(recs)} profile={profile}",
                    flush=True,
                )
            summary.documents_emitted += len(files)
        if dry_run:
            summary.chunks_written = len(all_records)
            summary.status = "ok"
            return summary
        written = write_harvest_input(session, rid, all_records)
        summary.chunks_written = written
        summary.status = "ok" if written else "degraded: no chunks"
        return summary

    print(
        json.dumps({"run_id": run_id, "cache": cache, "chunking": "docling"}, indent=2)
    )

    # Fresh queues — avoid content_hash dedupe from prior orch-docling runs.
    db_connect(cache)
    for model in (HarvestInput, KnowledgeQueueItem, DecisionQueueItem):
        deleted = sqla.session.query(model).delete(synchronize_session=False)
        print(f"cleared {model.__tablename__}: {deleted}", flush=True)
    sqla.session.commit()

    result = run_oie_pipeline(
        cache_file=cache,
        pipeline_run_id=run_id,
        sync_repos=False,
        run_harvester_fn=run_harvester,
        use_langgraph=True,
    )

    db_connect(cache)
    harvest = sqla.session.query(HarvestInput).filter_by(pipeline_run_id=run_id).count()
    knowledge = (
        sqla.session.query(KnowledgeQueueItem).filter_by(pipeline_run_id=run_id).count()
    )
    decisions = (
        sqla.session.query(DecisionQueueItem).filter_by(pipeline_run_id=run_id).all()
    )
    linked = sum(1 for d in decisions if d.status == "linked")
    review = sum(1 for d in decisions if d.status == "review_required")

    status = {
        "run_id": run_id,
        "orchestrator": json.loads(result.to_json()),
        "queues": {
            "harvest_input": harvest,
            "knowledge_queue": knowledge,
            "decision_queue": len(decisions),
            "linked": linked,
            "review_required": review,
        },
        "frameworks": {
            "stage_graph": "langgraph",
            "ingest_chunking": "llama-index DoclingReader/DoclingNodeParser (+ HybridChunker fallback)",
        },
    }
    ART.mkdir(parents=True, exist_ok=True)
    out = ART / "phase_a_status.json"
    out.write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))
    print(f"wrote {out}", flush=True)
    return 0 if result.to_dict()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
