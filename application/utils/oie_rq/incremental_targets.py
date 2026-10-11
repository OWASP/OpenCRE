"""Per-target skip / retry / failure reporting for exhaustive OIE reingest.

Skip when either:
  1. checkpoint SHA matches current HEAD and prior A→B→C drained successfully, or
  2. all harvest_input rows for the repo are processed and related KQ consumed.

Failed targets retry up to ``MAX_TARGET_ATTEMPTS`` then land in the FAILURES report.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from application.utils.harvester.schemas import HARVESTABLE_KINDS, RepositoryConfig

MAX_TARGET_ATTEMPTS = 5


@dataclass
class TargetOutcome:
    repo_id: str
    source_repo: str
    status: str  # skipped | ok | failed | exhausted
    attempts: int = 0
    skip_reason: str = ""
    error: str = ""
    head_sha: str = ""
    checkpoint_sha: str = ""


@dataclass
class FailureReport:
    run_id: str
    failures: List[TargetOutcome] = field(default_factory=list)
    skipped: List[TargetOutcome] = field(default_factory=list)
    succeeded: List[TargetOutcome] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "failures": [asdict(f) for f in self.failures],
            "skipped": [asdict(s) for s in self.skipped],
            "succeeded": [asdict(s) for s in self.succeeded],
            "failure_count": len(self.failures),
            "ok": len(self.failures) == 0,
        }


@dataclass
class RunStatus:
    """Canvas-facing progress snapshot (written as JSON)."""

    run_id: str
    phase: str
    as_of_utc: str
    total_targets: int = 0
    done: int = 0
    skipped: int = 0
    succeeded: int = 0
    failed: int = 0
    exhausted: int = 0
    in_progress: str = ""
    attempts_on_current: int = 0
    queue_queued: int = 0
    queue_started: int = 0
    eta_utc: str = ""
    eta_note: str = ""
    failures: List[Dict[str, Any]] = field(default_factory=list)
    score: Optional[Dict[str, Any]] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def harvestable_targets(
    repositories: Sequence[RepositoryConfig],
) -> List[RepositoryConfig]:
    wanted = set(HARVESTABLE_KINDS)
    return [r for r in repositories if r.enabled and r.kind in wanted]


def source_repo_for(cfg: RepositoryConfig) -> str:
    return f"{cfg.owner}/{cfg.repo}"


def _pending_hi_count(session: Any, source_repo: str) -> int:
    from application.database.db import HarvestInput

    return (
        session.query(HarvestInput)
        .filter_by(source_repo=source_repo, status="pending")
        .count()
    )


def _unconsumed_kq_for_source(session: Any, source_repo: str) -> int:
    """Count unconsumed knowledge_queue rows for ``source_repo``."""
    from application.database.db import KnowledgeQueueItem

    return (
        session.query(KnowledgeQueueItem)
        .filter(
            KnowledgeQueueItem.consumed_at.is_(None),
            KnowledgeQueueItem.source_repo == source_repo,
        )
        .count()
    )


def load_checkpoint_sha(session: Any, repo_id: str) -> str:
    from application.utils.harvester.checkpoint_store import CheckpointStore

    store = CheckpointStore(session)
    cp = store.load(repo_id)
    if not cp:
        return ""
    return (cp.last_processed_commit or "").strip()


def should_skip_target(
    session: Any,
    *,
    repo_id: str,
    source_repo: str,
    head_sha: str,
) -> tuple[bool, str]:
    """Return (skip?, reason).

    Skip when queues for this source are fully drained AND either the commit SHA
    matches the durable checkpoint (prior success) or HEAD could not be probed
    but a checkpoint already exists (treat as consumed).
    """
    head = (head_sha or "").strip()
    checkpoint = load_checkpoint_sha(session, repo_id)
    pending_hi = _pending_hi_count(session, source_repo)
    open_kq = _unconsumed_kq_for_source(session, source_repo)
    drained = pending_hi == 0 and open_kq == 0

    if not drained:
        return False, ""

    if head and checkpoint and head == checkpoint:
        return True, "sha_unchanged_and_prior_success"

    if drained and checkpoint and not head:
        return True, "all_hi_processed_kq_consumed"

    return False, ""


def record_attempt(
    outcome: TargetOutcome,
    *,
    ok: bool,
    error: str = "",
) -> TargetOutcome:
    outcome.attempts += 1
    if ok:
        outcome.status = "ok"
        outcome.error = ""
        return outcome
    outcome.error = error or outcome.error or "unknown"
    if outcome.attempts >= MAX_TARGET_ATTEMPTS:
        outcome.status = "exhausted"
    else:
        outcome.status = "failed"
    return outcome


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(path: Path, status: RunStatus) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status.to_dict(), indent=2) + "\n", encoding="utf-8")


def write_failure_report(path: Path, report: FailureReport) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")


def estimate_eta_utc(
    *,
    started_monotonic: float,
    done: int,
    total: int,
    now_monotonic: float,
) -> tuple[str, str]:
    """Return (eta_iso_or_empty, note)."""
    remaining = max(total - done, 0)
    if done <= 0 or remaining == 0:
        if remaining == 0 and total > 0:
            return "", "complete"
        return "", "warming up"
    elapsed = max(now_monotonic - started_monotonic, 1.0)
    per = elapsed / done
    seconds_left = per * remaining
    eta = datetime.now(timezone.utc).timestamp() + seconds_left
    eta_iso = datetime.fromtimestamp(eta, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    mins = int(seconds_left // 60)
    return eta_iso, f"~{mins}m left · {per/60:.1f}m/target"
