"""Where C's envelopes go once they are built.

Retiring a queue row is only safe if the envelope built from it survived
somewhere. A run that stamps ``consumed_at`` and drops the ``LinkProposal`` on
the floor has destroyed that chunk: B will not re-offer the row, and nothing
downstream ever saw the decision. So consumption is defined against a sink, not
against the pipeline having finished.

Two implementations here:

- ``JsonlEnvelopeSink`` — appends one JSON envelope per line. Durable, greppable,
  and enough to make a live drain lossless before the graph writer exists.
- ``NullEnvelopeSink`` — counts and discards, for dry runs. It reports
  ``persists=False``, and the runner refuses to consume behind it.

The graph / review-queue writers (W8b) become further implementations of the
same protocol, so the consumption rule does not have to change when they land.
"""

import logging
import os
from typing import List, Protocol, Sequence, Union

from application.utils.librarian.schemas import LinkProposal, ReviewItem

logger = logging.getLogger(__name__)

Envelope = Union[LinkProposal, ReviewItem]


class EnvelopeSink(Protocol):
    """Somewhere an envelope can be durably put."""

    @property
    def persists(self) -> bool:
        """True when a written envelope outlives the process.

        The runner reads this to decide whether retiring the source row would
        lose work; a sink that answers False can never trigger consumption.
        """
        ...

    def write(self, envelopes: Sequence[Envelope]) -> int:
        """Persist the batch; return how many were written."""
        ...


class NullEnvelopeSink:
    """Accepts envelopes and keeps nothing. For dry runs and tests."""

    def __init__(self) -> None:
        self.written = 0

    @property
    def persists(self) -> bool:
        return False

    def write(self, envelopes: Sequence[Envelope]) -> int:
        self.written += len(envelopes)
        return len(envelopes)


class JsonlEnvelopeSink:
    """Appends envelopes to a JSONL file, one RFC envelope per line.

    Append rather than truncate: several runs over different
    ``pipeline_run_id``s share one output file, and each envelope already
    carries its own run id. ``model_dump_json`` is used so the file holds the
    same RFC shape Module D will consume, datetimes and enums included.

    ``exclude_none=True`` is not cosmetic. The vendored RFC schemas type their
    optional fields as plain ``"string"`` and leave them out of ``required``,
    so an absent value must be an *absent key* — emitting ``"repo": null``
    fails validation against the very schema this file is supposed to satisfy.
    Every rss envelope trips it (no ``repo``/``commit_sha``), and so does every
    github one (no ``feed_url``/``post_guid``). Writing the null would hand
    Module D a file its own validator rejects.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes: Sequence[Envelope]) -> int:
        if not envelopes:
            return 0
        parent = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(parent, exist_ok=True)
        lines: List[str] = [e.model_dump_json(exclude_none=True) for e in envelopes]
        # One open/flush for the batch, and the newline goes after every record
        # so a partially written run still parses line by line.
        with open(self._path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        logger.info("wrote %d envelopes to %s", len(lines), self._path)
        return len(lines)


def envelope_id(envelope: Envelope) -> str:
    """The chunk an envelope speaks for — handy for logs and tests."""
    return envelope.chunk_id


__all__ = [
    "EnvelopeSink",
    "JsonlEnvelopeSink",
    "NullEnvelopeSink",
    "envelope_id",
]
