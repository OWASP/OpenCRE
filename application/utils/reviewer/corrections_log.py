"""The corrections log: every human verdict, append-only, one JSON per line.

The founding RFC (``docs/designs/owasp-pane-of-glass.md``, Module D) decides
this shape: "simple human oversight without db bloat" — verdicts append to a
JSONL log rather than growing new tables. The RFC's bonus tier, loss
warehousing, falls out for free: each record carries the ids needed to join
back to the full envelope, and ``decision_queue`` rows are never deleted, so
(input, prediction, human label) is always reconstructable without duplicating
the envelope into every line.

This log is the durable half of the two-step verdict flow: **record here first,
stamp ``consumed_at`` second.** A crash in between leaves the row unconsumed
and the verdict re-recordable. The reverse order would retire the row and lose
the one thing the human produced.

Like C's ``JsonlEnvelopeSink``, this makes no cross-process claims: two
services appending to one path can interleave. One reviewer service per log
file, which is the same single-consumer contract the queue itself carries.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

#: Bumped when a record gains/loses fields; readers filter on it.
CORRECTIONS_SCHEMA_VERSION = "0.1.0"


class ReviewVerdict(BaseModel):
    """One human decision about one ``review_required`` row."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CORRECTIONS_SCHEMA_VERSION
    #: decision_queue primary key — the join back to the full envelope.
    decision_row_id: str
    review_id: Optional[str]
    chunk_id: str
    pipeline_run_id: str
    #: why C routed this to a human, carried so the log is analysable alone.
    reason_code: Optional[str]
    #: B's label on the source chunk, for the same reason.
    source_label: Optional[str]
    verdict: Literal["approved", "rejected"]
    #: On approval: the CRE id the human confirmed (from suggested_links or
    #: typed). On rejection: None.
    approved_cre_id: Optional[str] = None
    reviewer: str
    reviewed_at: datetime


class JsonlCorrectionsLog:
    """Appends verdicts to a JSONL file, creating parent directories as needed."""

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def record(self, verdict: ReviewVerdict) -> None:
        """Append one verdict durably (flush + fsync before returning).

        The stamp on decision_queue happens only after this returns, so this
        write IS the persistence the retirement is gated on — same rule as C's
        "consumption is gated on persistence", one queue downstream.
        """
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload = verdict.model_dump(mode="json")
        # One canonical timestamp format: naive UTC ISO, exactly what
        # decision_queue itself stores, so joining the log to the queue never
        # fights offsets. Aware input is converted; naive input is taken as UTC,
        # the pipeline-wide convention.
        reviewed_at = verdict.reviewed_at
        if reviewed_at.tzinfo:
            reviewed_at = reviewed_at.astimezone(timezone.utc).replace(tzinfo=None)
        payload["reviewed_at"] = reviewed_at.isoformat()
        line = json.dumps(payload, sort_keys=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())


__all__ = ["CORRECTIONS_SCHEMA_VERSION", "JsonlCorrectionsLog", "ReviewVerdict"]
