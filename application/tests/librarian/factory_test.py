"""Tests for the component factory (the orchestrator's entry into Module C).

``build_components`` reaches for a live database and the cross-encoder, so the
test here fakes the database and patches the one heavy loader. That is still
worth doing rather than skipping: everything else in the function — the
``cre_defs`` import, the hub read, the pool build, the wiring of all three
stages — is code that only ever runs in production otherwise, and a typo in any
of it is a crash in the orchestrator's entry point.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

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
        if str(doc_type) != "CRE":
            return {}
        return self.embeddings

    def get_embedding_contents_by_doc_type(self, doc_type):
        if str(doc_type) != "CRE":
            return {}
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

    def test_exposes_hub_keys_as_emit_membership(self) -> None:
        """Without a CRE session, membership falls back to hub embedding keys."""
        self.assertEqual(
            self._build().cre_membership, frozenset({"616-305", "111-111"})
        )

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

    def test_cre_summary_replaces_c2_texts_and_can_use_in_memory_c1(self) -> None:
        hidden = {"616-305": "hidden password blurb", "111-111": "hidden session blurb"}
        vectors = {"616-305": [0.1, 0.2, 0.3], "111-111": [0.3, 0.2, 0.1]}
        with mock.patch(
            "application.utils.librarian.cross_encoder." "build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            with mock.patch.dict(
                os.environ,
                {
                    "CRE_LIBRARIAN_TEMPERATURE": "1.2",
                    "CRE_LIBRARIAN_CRE_SUMMARY": "1",
                },
                clear=True,
            ):
                with mock.patch(
                    "application.utils.librarian.cre_summary.inject_cre_summaries",
                    return_value=(hidden, vectors),
                ):
                    components = build_components(
                        _FakeDatabase(),
                        config=load_config(),
                        embed_fn=lambda text: [0.1, 0.2, 0.3],
                    )
        self.assertEqual(
            components.reranker._cre_texts["616-305"], "hidden password blurb"
        )
        from application.utils.librarian.candidate_retriever import CandidateRetriever

        self.assertIsInstance(components.retriever, CandidateRetriever)

    def test_dual_index_keeps_name_pool_and_summary_pool(self) -> None:
        hidden = {"616-305": "hidden password blurb", "111-111": "hidden session blurb"}
        vectors = {"616-305": [0.1, 0.2, 0.3], "111-111": [0.3, 0.2, 0.1]}
        with mock.patch(
            "application.utils.librarian.cross_encoder." "build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            with mock.patch.dict(
                os.environ,
                {
                    "CRE_LIBRARIAN_TEMPERATURE": "1.2",
                    "CRE_LIBRARIAN_CRE_SUMMARY": "1",
                    "CRE_LIBRARIAN_DUAL_INDEX": "1",
                    "CRE_LIBRARIAN_PRIOR_CAGE": "0",
                },
                clear=True,
            ):
                with mock.patch(
                    "application.utils.librarian.cre_summary.inject_cre_summaries",
                    return_value=(hidden, vectors),
                ):
                    components = build_components(
                        _FakeDatabase(),
                        config=load_config(),
                        embed_fn=lambda text: [0.1, 0.2, 0.3],
                    )
        from application.utils.librarian.dual_index_retriever import DualIndexRetriever

        self.assertIsInstance(components.retriever, DualIndexRetriever)

    def test_cre_summary_off_keeps_hub_texts(self) -> None:
        components = self._build()
        self.assertEqual(components.reranker._cre_texts["616-305"], "password storage")

    def test_standard_retrieval_flag_is_a_noop_without_a_standard_hub(self) -> None:
        with mock.patch(
            "application.utils.librarian.cross_encoder." "build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            with mock.patch.dict(
                os.environ,
                {
                    "CRE_LIBRARIAN_TEMPERATURE": "1.2",
                    "CRE_LIBRARIAN_STANDARD_RETRIEVAL": "1",
                },
                clear=True,
            ):
                components = build_components(
                    _FakeDatabase(),
                    config=load_config(),
                    embed_fn=lambda text: [0.1, 0.2, 0.3],
                )
        self.assertTrue(hasattr(components.retriever, "retrieve"))


if __name__ == "__main__":
    unittest.main()
