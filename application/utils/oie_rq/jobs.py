"""RQ callables for OIE A/B/C fan-out (import-worker style)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cre_logging import get_logger

logger = get_logger(__name__)


def _session(db_connection_str: str) -> Any:
    from application.cmd.cre_main import db_connect

    return db_connect(path=db_connection_str).session


def _pending_artifacts_for_repo(
    session: Any, pipeline_run_id: str, source_repo: str
) -> List[str]:
    from application.database.db import HarvestInput

    rows = (
        session.query(HarvestInput.artifact_id)
        .filter_by(
            pipeline_run_id=pipeline_run_id,
            status="pending",
            source_repo=source_repo,
        )
        .distinct()
        .all()
    )
    return sorted({str(r[0]) for r in rows if r[0]})


def run_oie_a_job(
    *,
    pipeline_run_id: str,
    repo_id: str,
    db_connection_str: str,
    source_repo: Optional[str] = None,
    repos_yaml: Optional[str] = None,
    sync_repos: bool = True,
    dry_run: bool = False,
    skip_b: bool = False,
    skip_c: bool = False,
) -> Dict[str, Any]:
    """Harvest one repository; enqueue B jobs per artifact written."""
    from application.utils.harvester.pipeline import run_harvester
    from application.utils.oie_rq.fanout import enqueue_b_jobs_for_artifacts

    session = _session(db_connection_str)
    summary = run_harvester(
        session,
        pipeline_run_id,
        repos_yaml=repos_yaml,
        dry_run=dry_run,
        sync_repos=sync_repos,
        repo_ids=[repo_id],
    )
    out: Dict[str, Any] = {
        "stage": "a",
        "repo_id": repo_id,
        "source_repo": source_repo,
        "summary": summary.to_json() if hasattr(summary, "to_json") else str(summary),
        "b_jobs": [],
    }
    if dry_run or skip_b:
        return out
    if not source_repo:
        logger.warning(
            "OIE A job repo_id=%s missing source_repo; skipping B enqueue", repo_id
        )
        return out
    artifacts = _pending_artifacts_for_repo(session, pipeline_run_id, source_repo)
    out["b_jobs"] = enqueue_b_jobs_for_artifacts(
        pipeline_run_id=pipeline_run_id,
        artifact_ids=artifacts,
        db_connection_str=db_connection_str,
        dry_run=dry_run,
        skip_c=skip_c,
    )
    return out


def _keep_all_for_artifact(
    session: Any, pipeline_run_id: str, artifact_id: str, *, dry_run: bool
) -> Any:
    """Eval-only: promote this artifact's pending harvest rows to KNOWLEDGE."""
    from application.database.db import HarvestInput
    from application.utils.noise_filter.hashing import compute_content_hash
    from application.utils.noise_filter.pipeline import RunSummary as BSummary
    from application.utils.noise_filter.queue_writer import write_verdicts
    from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult

    summary = BSummary(run_id=pipeline_run_id)
    rows = (
        session.query(HarvestInput)
        .filter_by(
            pipeline_run_id=pipeline_run_id,
            status="pending",
            artifact_id=artifact_id,
        )
        .all()
    )
    summary.read = len(rows)
    if dry_run:
        summary.kept_knowledge = len(rows)
        summary.status = "ok"
        return summary
    triples = []
    for row in rows:
        try:
            record = ChangeRecord.model_validate(row.payload)
        except Exception:  # noqa: BLE001
            summary.parse_errors += 1
            continue
        verdict = ClassifyResult(
            label="KNOWLEDGE",
            confidence=1.0,
            reasoning="oie-rq-keep-all-knowledge",
        )
        triples.append((record, verdict, compute_content_hash(record.text)))
        row.status = "processed"
        summary.kept_knowledge += 1
    stats = write_verdicts(session, triples)
    summary.inserted = stats.inserted
    summary.deduped = stats.deduped
    session.commit()
    summary.status = "ok"
    return summary


def run_oie_b_job(
    *,
    pipeline_run_id: str,
    artifact_id: str,
    db_connection_str: str,
    dry_run: bool = False,
    skip_c: bool = False,
) -> Dict[str, Any]:
    """Classify one Docling document; enqueue C for that artifact."""
    import os

    from application.utils.noise_filter.pipeline import run_noise_filter
    from application.utils.oie_rq.fanout import enqueue_c_job

    session = _session(db_connection_str)
    keep_all = os.environ.get("CRE_OIE_KEEP_ALL_KNOWLEDGE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if keep_all:
        summary = _keep_all_for_artifact(
            session, pipeline_run_id, artifact_id, dry_run=dry_run
        )
    else:
        summary = run_noise_filter(
            session,
            pipeline_run_id,
            artifact_id=artifact_id,
            dry_run=dry_run,
        )
    out: Dict[str, Any] = {
        "stage": "b",
        "artifact_id": artifact_id,
        "summary": summary.to_json() if hasattr(summary, "to_json") else str(summary),
        "c_job": None,
    }
    if dry_run or skip_c:
        return out
    out["c_job"] = enqueue_c_job(
        pipeline_run_id=pipeline_run_id,
        artifact_id=artifact_id,
        db_connection_str=db_connection_str,
        dry_run=dry_run,
    )
    return out


def run_oie_c_job(
    *,
    pipeline_run_id: str,
    artifact_id: str,
    db_connection_str: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Drain knowledge_queue for one Docling document."""
    from application.cmd.cre_main import db_connect
    from application.utils.librarian.config_loader import load_config
    from application.utils.librarian.envelope_sink import (
        DbEnvelopeSink,
        NullEnvelopeSink,
    )
    from application.utils.librarian.factory import build_components
    from application.utils.librarian.queue_runner import run_librarian_queue

    cfg = load_config()
    database = db_connect(path=db_connection_str)
    components = build_components(database, config=cfg)
    sink = (
        NullEnvelopeSink()
        if dry_run
        else DbEnvelopeSink(database.session, pipeline_run_id)
    )
    summary = run_librarian_queue(
        database.session,
        pipeline_run_id,
        components,
        cfg,
        at=datetime.now(timezone.utc),
        sink=sink,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )
    return {
        "stage": "c",
        "artifact_id": artifact_id,
        "summary": summary.to_json() if hasattr(summary, "to_json") else str(summary),
    }
