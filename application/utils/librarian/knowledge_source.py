"""Where Module C reads accepted chunks from.

Defines the source interface plus a fixture-backed stub for testing. The real
DB-backed source (polling Module B's knowledge_queue table) lands W8 and yields
the same KnowledgeQueueItem rows; C synthesizes the RFC KnowledgeItem envelope
from each row at processing time (master guide §1.2).
"""

import logging
from abc import ABC, abstractmethod
from typing import Iterator

from pydantic import ValidationError

from application.utils.librarian.schemas import KnowledgeQueueItem

logger = logging.getLogger(__name__)


class KnowledgeSource(ABC):
    @abstractmethod
    def items(self) -> Iterator[KnowledgeQueueItem]:
        """Yield knowledge_queue rows awaiting classification."""
        raise NotImplementedError


class FixtureKnowledgeSource(KnowledgeSource):
    """Reads knowledge_queue rows from a JSONL fixture (one JSON object per line)."""

    def __init__(self, jsonl_path: str) -> None:
        self._path = jsonl_path

    def items(self) -> Iterator[KnowledgeQueueItem]:
        with open(self._path, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if line:
                    try:
                        yield KnowledgeQueueItem.model_validate_json(line)
                    except ValidationError as exc:
                        # Log only error locations/types, never the raw input —
                        # queue rows can carry sensitive content.
                        logger.warning(
                            "Skipping malformed knowledge_queue row at line %d: %s",
                            line_no,
                            exc.errors(include_input=False),
                        )
                        continue
