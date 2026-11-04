"""Phase 2: prose holes, chunk quality, ingest adapter (mocked loaders)."""

import tempfile
import unittest
from pathlib import Path

from application.utils.rag_parity.flags import RagParityFlags
from application.utils.rag_parity.phase2_chunk_quality import Chunk, filter_chunks
from application.utils.rag_parity.phase2_ingest import ingest_path_to_writer
from application.utils.rag_parity.phase2_prose import (
    find_prose_holes,
    prefer_richer_prose,
)


def _pci() -> str:
    return (
        "Requirement 3.4: Render PAN unreadable anywhere it is stored "
        "by using strong cryptography, truncation, or index tokens so that "
        "a compromise of one store does not expose the full primary account number."
    )


def _nist_junk() -> str:
    return (
        "An official website of the United States government "
        "skip to content navigation menu unauthorized frame window "
        "You have JavaScript disabled."
    )


class ProseHolesTest(unittest.TestCase):
    def test_finds_empty_junk_and_keeps_prose(self) -> None:
        holes = find_prose_holes(
            [
                ("n1", "PCI", _pci()),
                ("n2", "NIST", _nist_junk()),
                ("n3", "Empty", ""),
            ]
        )
        reasons = {h.node_id: h.reason for h in holes}
        self.assertNotIn("n1", reasons)
        self.assertEqual(reasons["n2"], "junk")
        self.assertEqual(reasons["n3"], "empty")

    def test_prefer_richer_prose(self) -> None:
        self.assertIn("Render PAN", prefer_richer_prose(_nist_junk(), _pci()))
        self.assertEqual(prefer_richer_prose(_pci(), _nist_junk()), _pci())


class ChunkQualityTest(unittest.TestCase):
    def test_rejects_junk_accepts_prose(self) -> None:
        report = filter_chunks(
            [Chunk(_nist_junk(), "a"), Chunk(_pci(), "b")],
            min_chars=40,
        )
        self.assertEqual(len(report.accepted), 1)
        self.assertIn("Render PAN", report.accepted[0].text)
        self.assertEqual(len(report.rejected), 1)


class IngestAdapterTest(unittest.TestCase):
    def test_injected_loader_writes_via_writer(self) -> None:
        written: list[tuple[str, str]] = []

        class W:
            def upsert_prose(self, *, node_id: str, text: str, source: str) -> None:
                written.append((node_id, text))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"
            path.write_text("placeholder", encoding="utf-8")
            result = ingest_path_to_writer(
                str(path),
                node_id="node-1",
                writer=W(),
                flags=RagParityFlags(ingest_pipeline=True),
                loader=lambda _p: [Chunk(_pci(), source="mock")],
            )
        self.assertEqual(result.written, 1)
        self.assertEqual(written[0][0], "node-1")
        self.assertIn("Render PAN", written[0][1])


if __name__ == "__main__":
    unittest.main()
