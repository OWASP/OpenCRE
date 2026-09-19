from cre_logging import get_logger

logger = get_logger(__name__)

import os
import unittest
from dataclasses import FrozenInstanceError
from typing import ClassVar, Dict
from unittest import mock

from application.utils.librarian.config_loader import LibrarianConfig, load_config
from application.utils.librarian.cross_encoder import HYBRID_BETA, HYBRID_GAMMA


class TestConfigLoaderDefaults(unittest.TestCase):
    def test_defaults_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.retriever_backend, "in_memory")
        self.assertEqual(cfg.crossencoder_model, "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.assertEqual(cfg.top_k_retrieval, 20)
        self.assertEqual(cfg.top_k_rerank, 5)
        self.assertEqual(cfg.link_threshold, 0.8)
        # 1.0 is the identity transform: an honestly *uncalibrated* softmax,
        # rather than a temperature nobody fitted.
        self.assertEqual(cfg.temperature, 1.0)
        self.assertEqual(cfg.batch_size, 32)
        self.assertEqual(cfg.ece_target, 0.10)
        self.assertEqual(cfg.conformal_alpha, 0.10)
        self.assertFalse(cfg.standard_retrieval)
        self.assertEqual(cfg.standard_retrieval_families, ())
        self.assertEqual(cfg.standard_top_k, 10)
        self.assertEqual(cfg.standard_max_cres_per_hit, 4)
        self.assertFalse(cfg.cre_text_enrich)
        self.assertFalse(cfg.cre_summary)
        self.assertFalse(cfg.dual_index)
        self.assertTrue(cfg.prior_cage)
        self.assertFalse(cfg.focus_query)
        self.assertTrue(cfg.pref_inject)
        self.assertTrue(cfg.prefer_audit_ids)
        self.assertAlmostEqual(cfg.hybrid_beta, 0.0)
        self.assertAlmostEqual(cfg.hybrid_gamma, 0.70)
        self.assertAlmostEqual(cfg.hybrid_beta, HYBRID_BETA)
        self.assertAlmostEqual(cfg.hybrid_gamma, HYBRID_GAMMA)

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
        "CRE_LIBRARIAN_TEMPERATURE": "1.208",
        "CRE_LIBRARIAN_BATCH_SIZE": "64",
        "CRE_LIBRARIAN_ECE_TARGET": "0.05",
        "CRE_LIBRARIAN_CONFORMAL_ALPHA": "0.20",
        "CRE_LIBRARIAN_STANDARD_RETRIEVAL": "1",
        "CRE_LIBRARIAN_STANDARD_RETRIEVAL_FAMILIES": "PCI DSS, ISO 27001",
        "CRE_LIBRARIAN_STANDARD_TOP_K": "8",
        "CRE_LIBRARIAN_CRE_TEXT_ENRICH": "true",
        "CRE_LIBRARIAN_CRE_SUMMARY": "1",
        "CRE_LIBRARIAN_DUAL_INDEX": "1",
        "CRE_LIBRARIAN_PRIOR_CAGE": "0",
        "CRE_LIBRARIAN_FOCUS_QUERY": "true",
        "CRE_LIBRARIAN_PREF_INJECT": "off",
        "CRE_LIBRARIAN_PREFER_AUDIT_IDS": "no",
        "CRE_LIBRARIAN_HYBRID_BETA": "3.0",
        "CRE_LIBRARIAN_HYBRID_GAMMA": "0.15",
    }

    def test_env_overrides_apply(self):
        with mock.patch.dict(os.environ, self.OVERRIDES, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.retriever_backend, "pgvector")
        self.assertEqual(cfg.crossencoder_model, "cross-encoder/other")
        self.assertEqual(cfg.top_k_retrieval, 50)
        self.assertEqual(cfg.top_k_rerank, 10)
        self.assertAlmostEqual(cfg.link_threshold, 0.7)
        self.assertAlmostEqual(cfg.temperature, 1.208)
        self.assertEqual(cfg.batch_size, 64)
        self.assertAlmostEqual(cfg.ece_target, 0.05)
        self.assertAlmostEqual(cfg.conformal_alpha, 0.20)
        self.assertTrue(cfg.standard_retrieval)
        self.assertEqual(cfg.standard_retrieval_families, ("PCI DSS", "ISO 27001"))
        self.assertEqual(cfg.standard_top_k, 8)
        self.assertTrue(cfg.cre_text_enrich)
        self.assertTrue(cfg.cre_summary)
        self.assertTrue(cfg.dual_index)
        self.assertFalse(cfg.prior_cage)
        self.assertTrue(cfg.focus_query)
        self.assertFalse(cfg.pref_inject)
        self.assertFalse(cfg.prefer_audit_ids)
        self.assertAlmostEqual(cfg.hybrid_beta, 3.0)
        self.assertAlmostEqual(cfg.hybrid_gamma, 0.15)

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

    def test_non_positive_temperature_raises(self):
        """T divides the logits, so zero or negative is undefined, not merely a
        bad setting — the same guard TemperatureScaler applies."""
        for value in ("0", "-1.5", "nan"):
            with self.subTest(value=value):
                with mock.patch.dict(
                    os.environ, {"CRE_LIBRARIAN_TEMPERATURE": value}, clear=True
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
