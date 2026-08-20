"""The C.4 safety seam: the blocking flags ``decide()`` already accepts.

``decide()`` has taken ``adversarial`` / ``update_ambiguous`` since W6, but no
caller ever passed them, so ``ADVERSARIAL_FLAG`` and ``UPDATE_AMBIGUOUS`` could
not fire from the pipeline — flagged on #991, and called out there as something
that must be wired before any write-back. This module is that wiring.

What is **not** here is a detector. The real guard (out-of-distribution scoring,
conformal prediction, update detection) is later work. So the seam ships with
``NullSafetyGuard``, which evaluates nothing and says so: its verdict carries
``evaluated=False``, the pipeline counts those rows, and the runner reports the
count. That distinction is the whole point — W5's review turned on a gate that
skipped and still reported success, and an unevaluated safety path that looks
identical to a clean one is the same failure wearing a different hat.

The rule this establishes for W8b: **a writer that commits links into the graph
must refuse to run behind a guard that reports ``evaluated=False``.** Retiring a
queue row without the safety path is recoverable — the envelope is still on
disk. Committing a link into a graph other tools read as truth is not.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from application.utils.librarian.section_validator import Section

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyVerdict:
    """Blocking flags for one chunk, plus whether anything actually looked.

    ``evaluated=False`` means no detector ran, so the two flags below are
    defaults rather than findings. A caller must never read ``adversarial=False``
    from an unevaluated verdict as "this chunk is safe".
    """

    adversarial: bool = False
    update_ambiguous: bool = False
    evaluated: bool = False

    @property
    def blocks_auto_link(self) -> bool:
        return self.adversarial or self.update_ambiguous


class SafetyGuard(Protocol):
    """Scores one section for the conditions that force human review."""

    def evaluate(self, section: Section) -> SafetyVerdict: ...


class NullSafetyGuard:
    """The declared-degraded guard: wires the seam, detects nothing.

    Deliberately not a lambda returning ``(False, False)`` — the named type and
    the ``evaluated=False`` verdict are what keep "we checked and it is clean"
    distinguishable from "nobody checked" everywhere downstream.
    """

    def evaluate(self, section: Section) -> SafetyVerdict:
        return SafetyVerdict(evaluated=False)


__all__ = ["NullSafetyGuard", "SafetyGuard", "SafetyVerdict"]
