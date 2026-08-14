from dataclasses import dataclass

from llama_index.core import Document as LlamaDocument
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.schema import TextNode
from typing import cast


@dataclass(slots=True)
class ChunkInfo:
    text: str
    start_char_idx: int
    end_char_idx: int


class DocumentChunker:
    """
    Splits documents into semantically coherent chunks while
    preserving the original document text boundaries.
    """

    DEFAULT_BUFFER_SIZE = 1
    DEFAULT_BREAKPOINT_PERCENTILE = 95
    DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        breakpoint_percentile_threshold: int = DEFAULT_BREAKPOINT_PERCENTILE,
    ) -> None:
        self._embedding_model = embedding_model
        self._buffer_size = buffer_size
        self._breakpoint_percentile_threshold = breakpoint_percentile_threshold
        self._splitter: SemanticSplitterNodeParser | None = None

    def _get_splitter(self) -> SemanticSplitterNodeParser:
        if self._splitter is None:
            embed_model = HuggingFaceEmbedding(
                model_name=self._embedding_model,
            )

            self._splitter = SemanticSplitterNodeParser(
                buffer_size=self._buffer_size,
                breakpoint_percentile_threshold=self._breakpoint_percentile_threshold,
                embed_model=embed_model,
            )

        return self._splitter

    def chunk(self, text: str) -> list[ChunkInfo]:
        if not text.strip():
            return []

        document = LlamaDocument(text=text)

        nodes = self._get_splitter().get_nodes_from_documents([document])

        chunks: list[ChunkInfo] = []

        for node in nodes:
            text_node = cast(TextNode, node)

            start = text_node.start_char_idx
            end = text_node.end_char_idx

            if start is None or end is None:
                continue

            chunks.append(
                ChunkInfo(
                    text=text_node.get_content(),
                    start_char_idx=start,
                    end_char_idx=end,
                )
            )

        return chunks
