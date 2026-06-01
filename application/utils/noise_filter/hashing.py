"""Content hashing for Module B's deduplication key.

Module A's actual emission does not include a content_hash field. Module B
computes one on ingest by:

  1. Normalizing the chunk `text` per the v0.2 normalization rules:
     - Unicode NFC normalization
     - CRLF / CR -> LF
     - Trailing whitespace per line stripped
     - Leading / trailing blank lines stripped
     - Runs of spaces / tabs in prose collapsed to a single space
     - Whitespace inside ```fenced code blocks``` and <pre>...</pre>
       preserved verbatim
  2. Computing SHA-256 of the normalized text, hex-encoded, lowercase.

The hash populates `KnowledgeQueueItem.content_hash` and serves as the
`UNIQUE` dedup key: re-feeding identical content via two pipeline runs (or
two source repos that mirror the same doc) collapses to one queue row.

Future: if Module A starts emitting `content_hash`, set the config flag
`CRE_NOISE_FILTER_TRUST_A_HASH=true` to use theirs and skip recomputation.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Code-fence detection: triple-backtick blocks and <pre>...</pre>.
# Lazy match across newlines so adjacent fences don't merge.
_FENCE_RE = re.compile(r"```[^\n]*\n.*?\n```|<pre>.*?</pre>", re.DOTALL)

# Runs of horizontal whitespace (spaces, tabs) -- collapsed in prose only.
_PROSE_WS_RE = re.compile(r"[ \t]+")


def normalize_text(text: str) -> str:
    """Apply Module A contract v0.2 normalization rules to `text`.

    Args:
        text: raw chunk text as received from Module A.

    Returns:
        normalized text suitable for hashing or LLM input.

    The function is idempotent: normalize(normalize(x)) == normalize(x).
    """
    # 1. Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)
    # 2. Line ending normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3 + 5: rules 3 (trailing whitespace) and 5 (prose whitespace collapse)
    # apply to non-fence segments; rule 3 still applies inside fences but
    # rule 5 does not.
    parts: list[str] = []
    last = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(_process_prose(text[last : m.start()]))
        parts.append(_process_fence(m.group(0)))
        last = m.end()
    if last < len(text):
        parts.append(_process_prose(text[last:]))
    out = "".join(parts)

    # 4. Leading / trailing blank lines stripped (interior blank lines kept)
    return out.strip("\n")


def _process_prose(segment: str) -> str:
    """Rules 3 + 5: strip trailing whitespace per line, collapse prose runs."""
    return "\n".join(
        _PROSE_WS_RE.sub(" ", line).rstrip() for line in segment.split("\n")
    )


def _process_fence(segment: str) -> str:
    """Rule 3 only: strip trailing whitespace per line; preserve interior."""
    return "\n".join(line.rstrip() for line in segment.split("\n"))


def compute_content_hash(text: str) -> str:
    """Normalize `text` and return its SHA-256 hex digest (lowercase, 64 chars).

    This is the canonical dedup key for `knowledge_queue.content_hash`.
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = [
    "compute_content_hash",
    "normalize_text",
]
