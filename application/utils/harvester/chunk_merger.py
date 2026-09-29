"""Module A.2 — merge undersized / same-heading Docling leaves.

One algorithm for all sources. Per-repo ``ChunkingConfig.merge_profile`` only
sets knobs (requirements vs narrative). Runs after primary chunking and before
``ChunkRecordBuilder``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Sequence

from application.utils.harvester.chunk_record_builder import ChunkRecordBuilder
from application.utils.harvester.models import ChunkInfo, Document
from application.utils.harvester.requirement_ids import requirement_ids

if TYPE_CHECKING:
    from application.utils.harvester.schemas import ChunkingConfig

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def heading_path_for(document: Document, chunk: ChunkInfo) -> tuple[str, ...]:
    path = ChunkRecordBuilder._heading_path_for_chunk(document, chunk)
    return tuple(path)


def merge_heading_key(
    document: Document,
    chunk: ChunkInfo,
    *,
    profile: str,
) -> tuple[str, ...]:
    """Heading identity used for A.2 merge boundaries.

    ``narrative`` keeps only heading levels ≤ 2 (``#`` / ``##``) so ``###``
    crumbs under the same section merge — cheat-sheet / sheet-level grain.
    """
    if profile != "narrative":
        return heading_path_for(document, chunk)

    start_line, _ = ChunkRecordBuilder._line_range(
        document.text,
        chunk.start_char_idx,
        chunk.end_char_idx,
    )
    active = [
        heading
        for heading in document.heading_structure
        if heading.level <= 2 and heading.start_line <= start_line <= heading.end_line
    ]
    active.sort(key=lambda heading: heading.start_line)
    path: list[str] = []
    for heading in active:
        while len(path) >= heading.level:
            path.pop()
        path.append(heading.text)
    return tuple(path)


def merge_chunks(
    document: Document,
    chunks: Sequence[ChunkInfo],
    config: "ChunkingConfig",
) -> List[ChunkInfo]:
    """Merge adjacent leaves under the same heading within token caps.

    Boundaries that always flush the buffer:
    - different merge-heading key (full path, or ``##`` grain for narrative)
    - ``split_on_requirement_id`` and ``b`` introduces a new id not in the buffer
    - ``tokens(buffer)+tokens(b) > merge_max_tokens``
    """
    if not chunks:
        return []
    profile = getattr(config, "merge_profile", "none") or "none"
    if profile == "none":
        min_tokens = int(config.merge_min_tokens or 0)
        if min_tokens <= 0:
            return list(chunks)

    max_tokens = int(config.merge_max_tokens or config.max_tokens)
    min_tokens = int(config.merge_min_tokens or 0)
    split_req = bool(config.split_on_requirement_id)

    merged: List[ChunkInfo] = []
    buf: List[ChunkInfo] = [chunks[0]]
    buf_heading = merge_heading_key(document, chunks[0], profile=profile)
    buf_ids = set(requirement_ids(chunks[0].text))
    buf_tokens = estimate_tokens(chunks[0].text)

    def flush() -> None:
        nonlocal buf, buf_heading, buf_ids, buf_tokens
        if not buf:
            return
        merged.append(_join(buf))
        buf = []
        buf_heading = tuple()
        buf_ids = set()
        buf_tokens = 0

    for chunk in chunks[1:]:
        hp = merge_heading_key(document, chunk, profile=profile)
        ids = requirement_ids(chunk.text)
        tok = estimate_tokens(chunk.text)

        new_req_boundary = False
        if split_req and ids:
            if buf_ids and ids.isdisjoint(buf_ids):
                new_req_boundary = True
            elif not buf_ids and len(ids) > 1:
                new_req_boundary = buf_tokens >= min_tokens

        fits = buf_tokens + tok <= max_tokens
        same_heading = hp == buf_heading

        if same_heading and fits and not new_req_boundary:
            buf.append(chunk)
            buf_tokens += tok
            buf_ids |= set(ids)
            continue

        flush()
        buf = [chunk]
        buf_heading = hp
        buf_ids = set(ids)
        buf_tokens = tok

    flush()

    if min_tokens <= 0 or len(merged) < 2:
        return merged

    tightened: List[ChunkInfo] = [merged[0]]
    for chunk in merged[1:]:
        prev = tightened[-1]
        prev_hp = merge_heading_key(document, prev, profile=profile)
        hp = merge_heading_key(document, chunk, profile=profile)
        prev_tok = estimate_tokens(prev.text)
        tok = estimate_tokens(chunk.text)
        if (
            hp == prev_hp
            and prev_tok < min_tokens
            and prev_tok + tok <= max_tokens
            and not (
                split_req
                and requirement_ids(chunk.text)
                and requirement_ids(prev.text)
                and requirement_ids(chunk.text).isdisjoint(requirement_ids(prev.text))
            )
        ):
            tightened[-1] = _join([prev, chunk])
        else:
            tightened.append(chunk)
    return tightened


def _join(parts: Sequence[ChunkInfo]) -> ChunkInfo:
    text = "\n\n".join(p.text.strip() for p in parts if p.text.strip())
    return ChunkInfo(
        text=text,
        start_char_idx=parts[0].start_char_idx,
        end_char_idx=parts[-1].end_char_idx,
    )
