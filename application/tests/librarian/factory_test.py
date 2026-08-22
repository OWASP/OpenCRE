"""Tests for the component factory (the orchestrator's entry into Module C).

``build_components`` reaches for a live database and the cross-encoder, so the
test here fakes the database and patches the one heavy loader. That is still
worth doing rather than skipping: everything else in the function — the
``cre_defs`` import, the hub read, the pool build, the wiring of all three
stages — is code that only ever runs in production otherwise, and a typo in any
of it is a crash in the orchestrator's entry point.
"""

import os
import unittest
from unittest import mock

from application.utils.librarian.config_loader import load_config
from application.utils.librarian.factory import build_components, build_scaler


class BuildScalerTest(unittest.TestCase):
    def test_uses_the_configured_temperature(self) -> None:
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_TEMPERATURE": "1.208"}, clear=True
        ):
            scaler = build_scaler(load_config())
        self.assertAlmostEqual(scaler.temperature, 1.208)

    def test_default_temperature_warns_that_it_is_uncalibrated(self) -> None:
        """T=1.0 is a plain softmax. Running the C.4 threshold against an
        unfitted confidence is exactly the mistake W5 existed to prevent, so it
        has to be loud rather than silent."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertLogs(
                "application.utils.librarian.factory", level="WARNING"
            ) as logs:
                scaler = build_scaler(load_config())
        self.assertAlmostEqual(scaler.temperature, 1.0)
        self.assertIn("uncalibrated", "\n".join(logs.output).lower())

    def test_fitted_temperature_is_quiet(self) -> None:
        with mock.patch.dict(
            os.environ, {"CRE_LIBRARIAN_TEMPERATURE": "1.033"}, clear=True
        ):
            with mock.patch(
                "application.utils.librarian.factory.logger"
            ) as fake_logger:
                build_scaler(load_config())
        fake_logger.warning.assert_not_called()


class _FakeDatabase:
    """The two hub reads ``build_components`` makes, and nothing else."""

    def __init__(self) -> None:
        self.embeddings = {"616-305": [0.1, 0.2, 0.3], "111-111": [0.3, 0.2, 0.1]}
        self.texts = {"616-305": "password storage", "111-111": "session handling"}

    def get_embeddings_by_doc_type(self, doc_type):
        return self.embeddings

    def get_embedding_contents_by_doc_type(self, doc_type):
        return self.texts


class BuildComponentsTest(unittest.TestCase):
    def _build(self):
        # Only the cross-encoder load is patched — it pulls in torch. The rest
        # of the factory runs for real.
        with mock.patch(
            "application.utils.librarian.cross_encoder." "build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            with mock.patch.dict(
                os.environ, {"CRE_LIBRARIAN_TEMPERATURE": "1.2"}, clear=True
            ):
                return build_components(
                    _FakeDatabase(),
                    config=load_config(),
                    embed_fn=lambda text: [0.1, 0.2, 0.3],
                )

    def test_builds_all_three_stages(self) -> None:
        components = self._build()
        self.assertTrue(hasattr(components.retriever, "retrieve"))
        self.assertTrue(hasattr(components.reranker, "rerank"))
        # The configured temperature reaches C.3 rather than the 1.0 default.
        self.assertAlmostEqual(components.scaler.temperature, 1.2)
        self.assertTrue(0.0 < components.scaler.confidence([2.0, 0.0]) < 1.0)

    def test_exposes_the_hub_ids_as_the_link_registry(self) -> None:
        """These are the only ids C may link to, and what the explicit-reference
        fast path validates a cited id against."""
        self.assertEqual(self._build().known_cre_ids, frozenset({"616-305", "111-111"}))

    def test_embed_fn_is_injectable_so_no_paid_call_is_made(self) -> None:
        calls = []

        def embed(text):
            calls.append(text)
            return [0.1, 0.2, 0.3]

        with mock.patch(
            "application.utils.librarian.cross_encoder." "build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            components = build_components(
                _FakeDatabase(), config=load_config(), embed_fn=embed
            )
        components.retriever.retrieve("verify passwords")
        self.assertEqual(calls, ["verify passwords"])


if __name__ == "__main__":
    unittest.main()
