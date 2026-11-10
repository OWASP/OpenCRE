"""The corrections log: every human decision, append-only, one JSON per line.

The founding RFC (``docs/designs/owasp-pane-of-glass.md``, Module D) decides
this shape: "simple human oversight without db bloat", so decisions append to a
JSONL log rather than growing new tables. Each line is a ``HumanDecision``, the
D -> feedback contract pinned in ``docs/owasp-graph/apis/module-d-hitl.md`` and
``schemas/human-decision.json``, and a test validates real lines against that
schema. ``chunk_id`` plus ``pipeline_run_id`` joins a line back to its one
``decision_queue`` row (``review_id`` alone repeats across runs), and those rows
are never deleted, so (input, prediction, human label) stays reconstructable even
for a line that carries no ``loss_event``.

Replaying a review appends a second line for the same row. The log stays
append-only, so readers take the **last** line per ``(review_id, pipeline_run_id)``.

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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional


def _fsync_dir_chain(path: str) -> None:
    """fsync every directory from ``path`` up to the filesystem root.

    ``os.fsync`` on the file makes its *contents* durable, not its *directory
    entry*: a crash after creating the file can lose the file itself unless the
    parent directory is synced, and the same holds for each directory
    ``os.makedirs`` created above it. Which ancestors are newly created cannot
    be detected without racing a concurrent ``record()``, so the whole chain is
    synced on every record. Records are human-paced, so the cost is noise.

    Platforms that cannot fsync a directory (or deny it, e.g. on ``/``) raise
    ``OSError``; those levels are skipped, which leaves durability no worse
    than it was before the attempt.
    """
    current = os.path.abspath(path)
    while True:
        try:
            fd = os.open(current, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


from pydantic import BaseModel, ConfigDict, Field, model_validator

from application.utils.librarian.schemas import SCHEMA_VERSION, ProposedLink


class RejectionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
    reason_message: Optional[str] = None


class LossEvent(BaseModel):
    """Pro-mode training capture: what the pipeline got wrong, and the fix."""

    model_config = ConfigDict(extra="allow")

    module: Literal["B", "C"]
    input_snapshot: Dict[str, Any]
    wrong_prediction: Dict[str, Any]
    correct_label: Dict[str, Any]
    notes: Optional[str] = None


class UiMeta(BaseModel):
    """Timing for the RFC's 3-second experiment."""

    model_config = ConfigDict(extra="allow")

    review_duration_ms: Optional[int] = Field(default=None, ge=0)
    keybind_used: Optional[str] = None


class HumanDecision(BaseModel):
    """One human decision about one review item (``human-decision.json``)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION, pattern=r"^0\.\d+\.\d+$")
    decision_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    review_id: str
    chunk_id: str
    pipeline_run_id: str
    decided_at: datetime
    decided_by: str = Field(min_length=1)
    action: Literal["approve", "reject", "correct"]
    #: Ground truth CRE links, on approve and correct.
    final_links: Optional[List[ProposedLink]] = None
    #: Why, on reject.
    rejection: Optional[RejectionDetail] = None
    loss_event: Optional[LossEvent] = None
    ui: Optional[UiMeta] = None

    @model_validator(mode="after")
    def _action_matches_its_payload(self) -> "HumanDecision":
        if self.action == "reject":
            if self.rejection is None or self.final_links:
                raise ValueError("reject needs rejection and no final_links")
        elif not self.final_links or self.rejection is not None:
            raise ValueError(f"{self.action} needs final_links and no rejection")
        return self


class JsonlCorrectionsLog:
    """Appends decisions to a JSONL file, creating parent directories as needed."""

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def record(self, decision: HumanDecision) -> None:
        """Append one decision durably (flush + fsync before returning).

        The stamp on decision_queue happens only after this returns, so this
        write IS the persistence the retirement is gated on, the same rule as
        C's "consumption is gated on persistence", one queue downstream.
        """
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # The schema has no nulls: an absent value must be an absent key.
        payload = decision.model_dump(mode="json", exclude_none=True)
        # RFC 3339 in UTC. Aware input is converted; naive input is taken as UTC,
        # the pipeline-wide convention.
        decided_at = decision.decided_at
        if decided_at.tzinfo:
            decided_at = decided_at.astimezone(timezone.utc).replace(tzinfo=None)
        payload["decided_at"] = decided_at.isoformat() + "Z"
        line = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        with open(self._path, "a+b") as fh:
            # A crash mid-write leaves a line with no newline. Without this the
            # next record would join it and be lost to every reader.
            if fh.seek(0, os.SEEK_END) > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    line = b"\n" + line
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        # The file's contents are durable; now make its directory entry (and
        # any directories makedirs created above it) durable too.
        _fsync_dir_chain(os.path.dirname(self._path) or ".")


__all__ = [
    "HumanDecision",
    "JsonlCorrectionsLog",
    "LossEvent",
    "RejectionDetail",
    "UiMeta",
]
