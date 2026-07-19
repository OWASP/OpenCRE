"""Module B pipeline orchestrator: harvest_input -> classify -> knowledge_queue.

This is the entry point the orchestrator invokes (via the CLI in cre.py). For a
given `pipeline_run_id` it reads Module A's pending rows from `harvest_input`,
runs the three-stage gate (regex -> sanitize -> LLM classifier), writes the
keepers to `knowledge_queue` (deduped), marks the input rows processed, and
returns a RunSummary the CLI prints as JSON for the orchestrator to consume.

Recall-first is preserved end to end: only NOISE is dropped; KNOWLEDGE and
UNCERTAIN always reach the queue.
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
from application.utils.noise_filter.llm_classifier import LLMClassifier
from application.utils.noise_filter.queue_writer import write_verdicts
from application.utils.noise_filter.regex_filter import RegexFilter
from application.utils.noise_filter.sanitize import sanitize_text
from application.utils.noise_filter.schemas import ChangeRecord

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
            logger.warning("harvest_input row %s failed validation: %s", row.id, e)

    # Stage 1: regex path filter (dropped = NOISE). Survivors get Stage 1.5 sanitize.
    regex = RegexFilter()
    survivors: list[ChangeRecord] = []
    for _row, record in parsed:
        is_noise, _reason = regex.is_noise_record(record)
        if is_noise:
            summary.dropped_noise += 1
        else:
            survivors.append(_sanitized(record))

    # Stage 2: LLM classify.
    classifier = classifier or LLMClassifier(config)
    verdicts = classifier.classify_batch(survivors)

    triples = [
        (rec, v, compute_content_hash(rec.text)) for rec, v in zip(survivors, verdicts)
    ]
    summary.kept_knowledge = sum(1 for _, v, _ in triples if v.label == "KNOWLEDGE")
    summary.kept_uncertain = sum(1 for _, v, _ in triples if v.label == "UNCERTAIN")
    summary.dropped_noise += sum(1 for _, v, _ in triples if v.label == "NOISE")

    if dry_run:
        return summary

    write = write_verdicts(session, triples)
    summary.inserted = write.inserted
    summary.deduped = write.deduped

    # Mark input rows so a re-run doesn't reprocess them.
    for row, _ in parsed:
        row.status = "processed"
    for row in failed:
        row.status = "error"
    session.commit()
    return summary


__all__ = ["RunSummary", "run_noise_filter"]
