"""Module A entry point: harvest OWASP repos → ``harvest_input``.

Shape mirrors Module B's ``run_noise_filter``:
``(session, pipeline_run_id, ..., dry_run) -> RunSummary`` with ``to_json()``.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Optional

from application.utils.harvester.change_detector import ChangeDetector
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
from application.utils.harvester.config_loader import load_repo_config
from application.utils.harvester.document_builder import DocumentBuilder
from application.utils.harvester.file_filter import FileFilter
from application.utils.harvester.git_repository_client import GitRepositoryClient
from application.utils.harvester.harvest_writer import write_harvest_input
from application.utils.harvester.incremental_pipeline import IncrementalPipeline
from application.utils.harvester.models import DiffBlock, Document
from application.utils.harvester.repos_validator import validate_repositories
from application.utils.harvester.schemas import RepositoryConfig
from application.utils.harvester.selection import select_repositories
from application.utils.harvester.source_resolver import resolve_sources


DEFAULT_REPOS_YAML = Path(__file__).with_name("repos.yaml")


@dataclass
class RunSummary:
    """Outcome of one Module A harvest run; the CLI emits this as JSON."""

    run_id: str
    repositories: int = 0
    opencre_repos: int = 0
    agent_repos: int = 0
    files_seen: int = 0
    files_retained: int = 0
    documents_emitted: int = 0
    chunks_written: int = 0
    errors: int = 0
    dry_run: bool = False
    status: str = "ok"
    skipped_not_due: int = 0
    deferred: int = 0
    repository_ids: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def run_harvester(
    session: Any,
    pipeline_run_id: str,
    *,
    repos_yaml: str | Path | None = None,
    dry_run: bool = False,
    sync_repos: bool = True,
    kinds: Optional[Collection[str]] = None,
    only_due: bool = False,
    max_repos: Optional[int] = None,
    now: Optional[datetime] = None,
) -> RunSummary:
    """
    Harvest configured repositories and stage chunks in ``harvest_input``.

    ``kinds`` / ``only_due`` / ``max_repos`` narrow the batch (see
    ``harvester.selection``); the defaults visit every enabled ``standard`` repo.
    ``sources`` org URLs are expanded here (indexer time) when present.

    For each enabled repo: optionally sync, detect files changed since the
    durable checkpoint, build documents, dedupe, chunk, validate as
    ChangeRecords, and insert pending ``harvest_input`` rows.
    """
    if not pipeline_run_id or not pipeline_run_id.strip():
        raise ValueError("run_harvester needs a non-empty pipeline_run_id")

    run_id = pipeline_run_id.strip()
    summary = RunSummary(run_id=run_id, dry_run=dry_run)

    repos_path = Path(repos_yaml) if repos_yaml else DEFAULT_REPOS_YAML
    repos_file = load_repo_config(repos_path)
    validate_repositories(repos_file)
    harvest_repos = repos_file.repositories
    if repos_file.sources:
        plan = resolve_sources(repos_file)
        summary.opencre_repos = len(plan.opencre)
        summary.agent_repos = len(plan.agent)
        summary.errors += len(plan.errors)
        harvest_repos = plan.opencre
        if plan.agent:
            logger.info(
                "harvester classified %s repo(s) for the OWASP agent",
                len(plan.agent),
            )

    checkpoint_store = CheckpointStore(session=session)
    builder = DocumentBuilder()

    selection = select_repositories(
        harvest_repos,
        checkpoint_store,
        kinds=kinds,
        only_due=only_due,
        max_repos=max_repos,
        now=now,
    )
    summary.skipped_not_due = selection.skipped_not_due
    summary.deferred = selection.deferred

    for repo_cfg in selection.selected:
        summary.repositories += 1
        summary.repository_ids.append(repo_cfg.id)
        try:
            written = _harvest_repository(
                session=session,
                repo_cfg=repo_cfg,
                pipeline_run_id=run_id,
                checkpoint_store=checkpoint_store,
                builder=builder,
                dry_run=dry_run,
                sync_repos=sync_repos,
                summary=summary,
            )
            summary.chunks_written += written
        except Exception:
            summary.errors += 1
            logger.exception(
                "harvester failed for repository %s/%s",
                repo_cfg.owner,
                repo_cfg.repo,
            )

    if summary.errors and summary.chunks_written == 0:
        summary.status = "degraded"
    elif summary.errors:
        summary.status = "degraded"
    return summary


def _harvest_repository(
    *,
    session: Any,
    repo_cfg: RepositoryConfig,
    pipeline_run_id: str,
    checkpoint_store: CheckpointStore,
    builder: DocumentBuilder,
    dry_run: bool,
    sync_repos: bool,
    summary: RunSummary,
) -> int:
    client = GitRepositoryClient(
        owner=repo_cfg.owner,
        repository=repo_cfg.repo,
        branch=repo_cfg.branch,
    )
    if sync_repos:
        client.sync()

    head = client.get_current_commit_sha()
    checkpoint = checkpoint_store.load(repo_cfg.id)
    base = checkpoint.last_processed_commit if checkpoint else None

    detector = ChangeDetector(client)
    if base:
        modified = detector.get_modified_files_since(base, head)
    else:
        # First run: every tracked file is a candidate. (Diffing against the git
        # empty tree does not work -- it is a tree, not a commit, so it cannot be
        # resolved as a base revision.)
        modified = detector.get_files_at_commit(head)

    file_filter = FileFilter(exclude_patterns=list(repo_cfg.paths.exclude))
    # Path include globs: keep files matching any include pattern.
    from pathspec import PathSpec

    include_spec = PathSpec.from_lines("gitignore", repo_cfg.paths.include)
    candidates = [
        path
        for path in modified
        if include_spec.match_file(path) and path in file_filter.filter_files([path])
    ]
    summary.files_seen += len(modified)
    summary.files_retained += len(candidates)

    committed_at = _commit_timestamp(client, head)
    documents: list[Document] = []
    for path in candidates:
        text = client.get_file_at_commit(head, path)
        block = DiffBlock(
            file_path=path,
            added_lines=[],
            repository=f"{repo_cfg.owner}/{repo_cfg.repo}",
            commit_sha=head,
            committed_at=committed_at,
        )
        documents.append(builder.build(block, text, pipeline_run_id))

    incremental = IncrementalPipeline(
        checkpoint_store=checkpoint_store,
        provider="github",
        owner=repo_cfg.owner,
        repository_name=repo_cfg.repo,
        branch=repo_cfg.branch,
        repository_id=repo_cfg.id,
    )
    emitted = incremental.process(
        repository=f"{repo_cfg.owner}/{repo_cfg.repo}",
        pipeline_run_id=pipeline_run_id,
        documents=documents,
        last_processed_commit=head,
        persist_checkpoint=False,
    )
    summary.documents_emitted += len(emitted)

    chunk_pipeline = DocumentChunkPipeline(chunking=repo_cfg.chunking)
    records = []
    for document in emitted:
        try:
            records.extend(chunk_pipeline.chunk(document))
        except Exception:
            # One malformed document must not discard the rest of the repo, and
            # retrying a deterministic failure every tick would only starve
            # other repos; it is counted and surfaces as a degraded run.
            summary.errors += 1
            logger.exception(
                "harvester could not chunk %s",
                document.locator.path or document.artifact_id,
            )

    written = write_harvest_input(session, pipeline_run_id, records, dry_run=dry_run)
    if not dry_run:
        incremental.save_checkpoint(pipeline_run_id, head)
    return written


def _commit_timestamp(client: GitRepositoryClient, commit_sha: str) -> datetime:
    import subprocess

    result = subprocess.run(
        [
            "git",
            "-C",
            str(client.get_local_path()),
            "show",
            "-s",
            "--format=%cI",
            commit_sha,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    raw = result.stdout.strip()
    # fromisoformat handles offsets; normalize Z.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).astimezone(timezone.utc)
