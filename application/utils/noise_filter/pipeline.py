"""Module B pipeline orchestrator: harvest_input -> classify -> knowledge_queue.

This is the entry point the orchestrator invokes (via the CLI in cre.py). For a
given `pipeline_run_id` it reads Module A's pending rows from `harvest_input`,
runs the three-stage gate (regex -> sanitize -> LLM classifier), writes the
keepers to `knowledge_queue` (deduped), marks handled input rows `processed`
(leaving infrastructure-failed ones `pending` for a later retry), and returns a
RunSummary the CLI prints as JSON for the orchestrator to consume.

Recall-first is preserved end to end: only NOISE is dropped; KNOWLEDGE and
UNCERTAIN always reach the queue. An LLM-call failure never finalizes a chunk as
a low-confidence verdict -- the row waits `pending` and is retried instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Optional

from pydantic import ValidationError

from application.database.db import HarvestInput
from application.utils.noise_filter.config_loader import NoiseFilterConfig, load_config
from application.utils.noise_filter.hashing import compute_content_hash
from application.utils.noise_filter.llm_classifier import (
    LLMClassifier,
    is_infra_failure,
)
from application.utils.noise_filter.queue_writer import write_verdicts
from application.utils.noise_filter.regex_filter import RegexFilter
from application.utils.noise_filter.sanitize import sanitize_text
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """Outcome of one Module B run; the CLI emits this as JSON."""

    run_id: str
    read: int = 0
    parse_errors: int = 0
    dropped_noise: int = 0  # regex-dropped + LLM NOISE
    kept_knowledge: int = 0
    kept_uncertain: int = 0
    inserted: int = 0
    deduped: int = 0
    retry_pending: int = 0  # infra-failed chunks left `pending` for a later retry
    dry_run: bool = False
    status: str = "ok"

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def _sanitized(record: ChangeRecord) -> ChangeRecord:
    """Stage 1.5: copy with sanitized text (no-op on clean input)."""
    try:
        clean = sanitize_text(record.text)
    except ValueError:
        return record  # sanitization emptied the text; keep original for the LLM
    return record.model_copy(update={"text": clean})


def run_noise_filter(
    session,
    pipeline_run_id: str,
    config: Optional[NoiseFilterConfig] = None,
    classifier: Optional[LLMClassifier] = None,
    *,
    dry_run: bool = False,
) -> RunSummary:
    """Classify one harvest run's chunks and enqueue the keepers.

    Args:
        session: SQLAlchemy session (caller owns connect/teardown).
        pipeline_run_id: the run to process (scopes the harvest_input rows).
        config: Module B settings; defaults to load_config().
        classifier: injectable LLMClassifier (tests pass a fake); default builds
            one from config.
        dry_run: classify but do not write to the queue or mark rows processed.
    """
    config = config or load_config()
    summary = RunSummary(run_id=pipeline_run_id, dry_run=dry_run)

    rows = (
        session.query(HarvestInput)
        .filter_by(pipeline_run_id=pipeline_run_id, status="pending")
        .all()
    )
    summary.read = len(rows)
    if not rows:
        return summary

    # Parse payloads -> ChangeRecord; invalid rows are counted and flagged.
    parsed: list[tuple[HarvestInput, ChangeRecord]] = []
    failed: list[HarvestInput] = []
    for row in rows:
        try:
            parsed.append((row, ChangeRecord.model_validate(row.payload)))
        except ValidationError as e:
            summary.parse_errors += 1
            failed.append(row)
            # Redact input snippets from logs (payload may carry repo secrets).
            logger.warning(
                "harvest_input row %s failed validation: %s",
                row.id,
                e.errors(include_input=False),
            )

    # Stage 1: regex path filter (dropped = NOISE). Survivors keep their input
    # row so an infra failure can leave that row `pending` for a later retry.
    regex = RegexFilter()
    survivors: list[tuple[HarvestInput, ChangeRecord]] = []
    for row, record in parsed:
        is_noise, _reason = regex.is_noise_record(record)
        if is_noise:
            summary.dropped_noise += 1
        else:
            survivors.append((row, record))

    # Stage 1.5 + Stage 2: sanitization is for the classifier's eyes only. We
    # hash and persist the ORIGINAL (canonical) text so the dedup key stays
    # stable across sanitizer changes and the queue keeps A's provenance; only a
    # sanitized copy reaches the LLM. Require exactly one verdict per survivor --
    # a misaligned classifier must fail loudly rather than let zip() truncate.
    classifier = classifier or LLMClassifier(config)
    verdicts = classifier.classify_batch([_sanitized(rec) for _row, rec in survivors])
    if len(verdicts) != len(survivors):
        raise RuntimeError(
            f"classifier returned {len(verdicts)} verdicts for "
            f"{len(survivors)} chunks; refusing to write a partial batch"
        )

    # An *infrastructure* failure (the LLM call itself failed) never really
    # classified the chunk. Rather than write a conf-0.0 UNCERTAIN row that
    # ON CONFLICT would then pin forever, leave that input row `pending` so a
    # later run retries it. Everything else -- genuine KNOWLEDGE/UNCERTAIN/NOISE,
    # or unparseable output -- is finalized.
    retry_rows: list[HarvestInput] = []
    triples: list[tuple[ChangeRecord, ClassifyResult, str]] = []
    for (row, record), verdict in zip(survivors, verdicts):
        if is_infra_failure(verdict):
            retry_rows.append(row)
        else:
            triples.append((record, verdict, compute_content_hash(record.text)))

    summary.kept_knowledge = sum(1 for _, v, _ in triples if v.label == "KNOWLEDGE")
    summary.kept_uncertain = sum(1 for _, v, _ in triples if v.label == "UNCERTAIN")
    summary.dropped_noise += sum(1 for _, v, _ in triples if v.label == "NOISE")
    summary.retry_pending = len(retry_rows)

    # Degraded only when the whole classified batch was infra failures (rate >=
    # failure_threshold, default 1.0) -- the CLI turns this into a non-zero exit
    # so the orchestrator retries the run. A partial failure stays "ok": the good
    # rows are committed and the failed ones wait `pending` for a natural retry.
    classified = len(survivors)
    if classified and summary.retry_pending / classified >= config.failure_threshold:
        summary.status = "degraded"

    if dry_run:
        return summary

    write = write_verdicts(session, triples)
    summary.inserted = write.inserted
    summary.deduped = write.deduped

    # Finalize every row except the infra-failed ones: NOISE-dropped and
    # classified rows become `processed`; infra-failed rows stay `pending` for a
    # retry; parse-failed rows are `error`.
    pending_ids = {row.id for row in retry_rows}
    for row, _ in parsed:
        if row.id not in pending_ids:
            row.status = "processed"
    for row in failed:
        row.status = "error"
    session.commit()
    return summary


__all__ = ["RunSummary", "run_noise_filter"]
