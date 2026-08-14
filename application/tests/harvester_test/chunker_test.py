import unittest
from unittest.mock import patch

from application.utils.harvester.chunker import (
    ChunkInfo,
    DocumentChunker,
)


class DocumentChunkerTests(unittest.TestCase):
    @patch("application.utils.harvester.chunker.HuggingFaceEmbedding")
    @patch("application.utils.harvester.chunker.SemanticSplitterNodeParser")
    def test_empty_document_returns_no_chunks(
        self,
        splitter_cls,
        embedding_cls,
    ):
        chunker = DocumentChunker()

        self.assertEqual(chunker.chunk(""), [])
        splitter_cls.assert_not_called()

    @patch("application.utils.harvester.chunker.HuggingFaceEmbedding")
    @patch("application.utils.harvester.chunker.SemanticSplitterNodeParser")
    def test_whitespace_document_returns_no_chunks(
        self,
        splitter_cls,
        embedding_cls,
    ):
        chunker = DocumentChunker()

        self.assertEqual(chunker.chunk("   \n\n  "), [])
        splitter_cls.assert_not_called()

    @patch("application.utils.harvester.chunker.HuggingFaceEmbedding")
    @patch("application.utils.harvester.chunker.SemanticSplitterNodeParser")
    def test_chunks_preserve_node_boundaries(
        self,
        splitter_cls,
        embedding_cls,
    ):
        node = type(
            "Node",
            (),
            {
                "start_char_idx": 0,
                "end_char_idx": 12,
                "get_content": lambda self: "# Heading\ntext",
            },
        )()

        splitter_cls.return_value.get_nodes_from_documents.return_value = [
            node,
        ]

        chunker = DocumentChunker()

        chunks = chunker.chunk("# Heading\ntext")

        self.assertEqual(
            chunks,
            [
                ChunkInfo(
                    text="# Heading\ntext",
                    start_char_idx=0,
                    end_char_idx=12,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
