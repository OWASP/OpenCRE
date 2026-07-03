import os
import unittest
from dataclasses import FrozenInstanceError
from typing import ClassVar, Dict
from unittest import mock

from application.utils.librarian.config_loader import LibrarianConfig, load_config


class TestConfigLoaderDefaults(unittest.TestCase):
    def test_defaults_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.retriever_backend, "in_memory")
        self.assertEqual(cfg.crossencoder_model, "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.assertEqual(cfg.top_k_retrieval, 20)
        self.assertEqual(cfg.top_k_rerank, 5)
        self.assertEqual(cfg.link_threshold, 0.8)
        self.assertEqual(cfg.batch_size, 32)
        self.assertEqual(cfg.ece_target, 0.10)
        self.assertEqual(cfg.conformal_alpha, 0.10)

    def test_config_is_frozen(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        with self.assertRaises(FrozenInstanceError):
            cfg.link_threshold = 0.5  # type: ignore[misc]


class TestConfigLoaderOverrides(unittest.TestCase):
    OVERRIDES: ClassVar[Dict[str, str]] = {
        "CRE_LIBRARIAN_RETRIEVER_BACKEND": "pgvector",
        "CRE_LIBRARIAN_CROSSENCODER_MODEL": "cross-encoder/other",
        "CRE_LIBRARIAN_TOP_K_RETRIEVAL": "50",
        "CRE_LIBRARIAN_TOP_K_RERANK": "10",
        "CRE_LIBRARIAN_LINK_THRESHOLD": "0.7",
        "CRE_LIBRARIAN_BATCH_SIZE": "64",
        "CRE_LIBRARIAN_ECE_TARGET": "0.05",
        "CRE_LIBRARIAN_CONFORMAL_ALPHA": "0.20",
    }

    def test_env_overrides_apply(self):
        with mock.patch.dict(os.environ, self.OVERRIDES, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.retriever_backend, "pgvector")
        self.assertEqual(cfg.crossencoder_model, "cross-encoder/other")
        self.assertEqual(cfg.top_k_retrieval, 50)
        self.assertEqual(cfg.top_k_rerank, 10)
        self.assertAlmostEqual(cfg.link_threshold, 0.7)
        self.assertEqual(cfg.batch_size, 64)
        self.assertAlmostEqual(cfg.ece_target, 0.05)
        self.assertAlmostEqual(cfg.conformal_alpha, 0.20)

    def test_bad_int_env_raises(self):
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_TOP_K_RETRIEVAL": "not-an-int"}, clear=True
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_link_threshold_above_one_raises(self):
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_LINK_THRESHOLD": "1.2"}, clear=True
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_negative_top_k_retrieval_raises(self):
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_TOP_K_RETRIEVAL": "-1"}, clear=True
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_rerank_greater_than_retrieval_raises(self):
        with mock.patch.dict(
            os.environ,
            {
                "CRE_LIBRARIAN_TOP_K_RETRIEVAL": "3",
                "CRE_LIBRARIAN_TOP_K_RERANK": "5",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                load_config()


if __name__ == "__main__":
    unittest.main()
