"""Requirement-id tokens used as Module A.2 merge fences.

Not a splitter — ``chunk_merger`` flushes when adjacent leaves introduce a
disjoint id set. The ASVS-only decimal regex missed NIST ``AC-2``, ISO
``A.5.1``, and similar, so those controls glued together.
"""

from __future__ import annotations

import re
from typing import FrozenSet

# Keep the original ASVS / OPC / PCI decimal capture (group 1).
_DECIMAL_ID_RE = re.compile(
    r"(?:\*?\*?V)?(\d+\.\d+(?:\.\d+)?)(?:\*?\*)?\b",
    re.IGNORECASE,
)
# NIST SP 800-53-style: AC-2, AU-12, AC-2(1).
_NIST_ID_RE = re.compile(
    r"\b([A-Z]{1,4}-\d{1,3}(?:\(\d+\))?)\b",
    re.IGNORECASE,
)
# ISO 27001 Annex A: A.5.1 / A.8.24.
_ISO_ID_RE = re.compile(
    r"\b([A-Z]\.\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)

_PATTERNS = (_DECIMAL_ID_RE, _NIST_ID_RE, _ISO_ID_RE)


def requirement_ids(text: str) -> FrozenSet[str]:
    """Return lowercased requirement ids found in ``text``."""
    found: set[str] = set()
    for pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            found.add(match.group(1).lower())
    return frozenset(found)


__all__ = ["requirement_ids"]
