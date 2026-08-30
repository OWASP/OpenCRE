from .models import ChunkInfo, Document
from .schemas import ChunkingConfig

__all__ = ["ChunkInfo", "DocumentChunker"]


class DocumentChunker:
    """
    Splits documents using the repository ``ChunkingConfig``.

    Strategies:
    - ``markdown_heading``: one chunk per heading section (plus preamble),
      then size-split oversized sections.
    - ``fixed_size``: sliding windows by approximate token budget.
    - ``html_readability``: treated as fixed_size until a dedicated parser exists.
    """

    # Rough chars-per-token for budget checks without a tokenizer dependency.
    CHARS_PER_TOKEN = 4

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self._config = config

    def chunk(self, text: str, *, document: Document | None = None) -> list[ChunkInfo]:
        if not text.strip():
            return []

        config = self._config
        if config is None:
            return self._fixed_size(text, max_tokens=1200, overlap_tokens=100)

        strategy = config.strategy
        if strategy == "markdown_heading" and document is not None:
            return self._markdown_heading(text, document, config)
        return self._fixed_size(
            text,
            max_tokens=config.max_tokens,
            overlap_tokens=config.overlap_tokens,
        )

    def _markdown_heading(
        self, text: str, document: Document, config: ChunkingConfig
    ) -> list[ChunkInfo]:
        headings = document.heading_structure
        if not headings:
            return self._fixed_size(
                text,
                max_tokens=config.max_tokens,
                overlap_tokens=config.overlap_tokens,
            )

        lines = text.splitlines(keepends=True)
        # Map 1-based line -> char offset of line start.
        line_starts = [0]
        for line in lines:
            line_starts.append(line_starts[-1] + len(line))

        sections: list[tuple[int, int]] = []
        first_heading_start = headings[0].start_line
        if first_heading_start > 1:
            sections.append((1, first_heading_start - 1))

        for heading in headings:
            sections.append((heading.start_line, heading.end_line))

        chunks: list[ChunkInfo] = []
        for start_line, end_line in sections:
            start_char = line_starts[start_line - 1]
            end_char = line_starts[min(end_line, len(lines))]
            section = text[start_char:end_char]
            if not section.strip():
                continue
            sized = self._fixed_size(
                section,
                max_tokens=config.max_tokens,
                overlap_tokens=config.overlap_tokens,
            )
            for piece in sized:
                chunks.append(
                    ChunkInfo(
                        text=piece.text,
                        start_char_idx=start_char + piece.start_char_idx,
                        end_char_idx=start_char + piece.end_char_idx,
                    )
                )
        return chunks

    def _fixed_size(
        self, text: str, *, max_tokens: int, overlap_tokens: int
    ) -> list[ChunkInfo]:
        window = max(1, max_tokens * self.CHARS_PER_TOKEN)
        overlap = min(max(0, overlap_tokens * self.CHARS_PER_TOKEN), window - 1)
        step = max(1, window - overlap)

        chunks: list[ChunkInfo] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + window, length)
            # Prefer breaking on a newline when not at EOF.
            if end < length:
                nl = text.rfind("\n", start + 1, end)
                if nl > start:
                    end = nl + 1
            piece = text[start:end]
            if piece.strip():
                chunks.append(
                    ChunkInfo(text=piece, start_char_idx=start, end_char_idx=end)
                )
            if end >= length:
                break
            start = start + step if step > 0 else end
            if start >= end:
                start = end
        return chunks
