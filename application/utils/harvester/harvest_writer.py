"""Persist Module A ChangeRecord payloads into ``harvest_input``."""

from __future__ import annotations

from typing import Any, Iterable

from application.database.db import HarvestInput
from application.utils.harvester.chunk_record_validator import ingest_record_to_payload
from application.utils.harvester.models import IngestChunkRecord


def write_harvest_input(
    session: Any,
    pipeline_run_id: str,
    records: Iterable[IngestChunkRecord],
    *,
    dry_run: bool = False,
) -> int:
    """
    Insert pending ``harvest_input`` rows for one pipeline run.

    Top-level ``pipeline_run_id`` matches the payload field (Module A contract).
    Returns the number of rows that would be / were written.
    """
    if not pipeline_run_id or not pipeline_run_id.strip():
        raise ValueError("pipeline_run_id must be non-empty")

    written = 0
    for record in records:
        if record.pipeline_run_id != pipeline_run_id:
            raise ValueError(
                f"record pipeline_run_id {record.pipeline_run_id!r} "
                f"!= harvest run {pipeline_run_id!r}"
            )
        payload = ingest_record_to_payload(record)
        if dry_run:
            written += 1
            continue
        session.add(
            HarvestInput(
                pipeline_run_id=pipeline_run_id,
                status="pending",
                payload=payload,
            )
        )
        written += 1

    if not dry_run and written:
        session.commit()
    return written
