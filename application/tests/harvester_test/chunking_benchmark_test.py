import os
import time
import unittest

from application.utils.harvester.chunker import DocumentChunker


@unittest.skipUnless(
    os.getenv("RUN_CHUNKING_BENCHMARK") == "1",
    "Chunking benchmark requires RUN_CHUNKING_BENCHMARK=1",
)
class ChunkingBenchmarkTests(unittest.TestCase):
    def test_chunking_benchmark(self):
        text = (
            "# Introduction\n\n" + "Python functions define reusable behavior. "
            "Variables store values and expressions compute results. "
            * 20
            + "\n\n## Architecture\n\n"
            + "The architecture separates ingestion from retrieval. "
            "Each component has a clearly defined responsibility. "
            * 20
            + "\n\n## Storage\n\n"
            + "Persistent state is protected by transactional operations. "
            "Commit and rollback provide atomicity and consistency. " * 20
        )

        start = time.perf_counter()

        chunks = DocumentChunker().chunk(text)

        elapsed = time.perf_counter() - start

        self.assertGreater(len(chunks), 0)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))
        self.assertTrue(
            all(
                0 <= chunk.start_char_idx < chunk.end_char_idx <= len(text)
                for chunk in chunks
            )
        )

        print(
            f"\nChunking benchmark: "
            f"{len(chunks)} chunks, "
            f"{elapsed:.3f}s, "
            f"input={len(text)} chars"
        )


if __name__ == "__main__":
    unittest.main()
