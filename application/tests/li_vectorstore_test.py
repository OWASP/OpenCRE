"""Hermetic tests for TASK-14.2 LI VectorStoreIndex adapter."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


class LiVstoreFlagTest(unittest.TestCase):
    def test_parity_alias_can_force_li_vstore_off(self) -> None:
        from application.utils.comprehension import flags

        with mock.patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("OWASP_CX_") or k.startswith("CRE_RAG_PARITY_"):
                    os.environ.pop(k, None)
            self.assertTrue(flags.on("LI_VSTORE"))  # DEFAULT_ON (TASK-14.8)
            os.environ["CRE_RAG_PARITY_LI_VSTORE"] = "0"
            self.assertFalse(flags.on("LI_VSTORE"))
            os.environ.pop("CRE_RAG_PARITY_LI_VSTORE")

    def test_li_vstore_default_on(self) -> None:
        from application.utils.comprehension import flags

        with mock.patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("OWASP_CX_") or k.startswith("CRE_RAG_PARITY_"):
                    os.environ.pop(k, None)
            self.assertTrue(flags.on("LI_VSTORE"))
            self.assertIn("LI_VSTORE", flags.DEFAULT_ON)
            self.assertIn("LI_RETRIEVE", flags.DEFAULT_ON)


class LiVectorstoreModuleTest(unittest.TestCase):
    def test_module_uses_vectorstoreindex_not_disk_sot(self) -> None:
        src = Path("application/utils/comprehension/li_vectorstore.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("VectorStoreIndex.from_vector_store", src)
        self.assertIn("BasePydanticVectorStore", src)
        self.assertIn("read-only", src.lower())
        self.assertIn("_dense", src)
        # Must not create a second persist dir / SimpleVectorStore SoT
        self.assertNotIn("persist_dir", src)
        self.assertNotIn("SimpleVectorStore", src)

    def test_retrieve_wires_li_vstore_flag(self) -> None:
        src = Path("application/utils/comprehension/retrieve.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('flags.on("LI_VSTORE")', src)
        self.assertIn("fetch_hits_via_vectorstore", src)

    def test_fetch_hits_via_vectorstore_roundtrip_with_stub_dense(self) -> None:
        from application.utils.comprehension import li_vectorstore
        from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, LaneHit

        if not li_vectorstore.li_vectorstore_available():
            self.skipTest("llama_index not installed")

        fake_hit = LaneHit(
            channel=CHANNEL_AGENT,
            score=0.91,
            embedding_id="1",
            content="password hashing guidance",
            url="owasp-agent://evidence/comprehension-asvs-raw-001",
            doc_type="chunk",
        )

        def fake_embed(texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

        with mock.patch(
            "application.utils.comprehension.retrieve._dense",
            return_value=[fake_hit],
        ):
            out = li_vectorstore.fetch_hits_via_vectorstore(
                conn=SimpleNamespace(),
                texts=["how to hash passwords?"],
                embed_many=fake_embed,
                limit=5,
                where_sql="embeddings_url LIKE 'owasp-agent://evidence/comprehension-%'",
            )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].url, fake_hit.url)
        self.assertIn("password", out[0].content)


if __name__ == "__main__":
    unittest.main()
