"""Fill-if-missing OIE base metadata + fail-loud gate."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from typing import Any, Dict, Mapping
from unittest import mock

from application.utils.librarian.oie_taxonomy import (
    OieMetadataNotPopulatedError,
    apply_oie_fill_if_missing,
    cre_oie_populated,
    require_oie_base_metadata,
    set_default_taxonomy_index,
)


class ApplyOieFillIfMissingTest(unittest.TestCase):
    def test_fills_empty(self) -> None:
        new_meta, action = apply_oie_fill_if_missing({}, {"class_id": "x"}, force=False)
        self.assertEqual(action, "updated")
        assert new_meta is not None
        self.assertEqual(new_meta["oie"]["class_id"], "x")

    def test_skips_existing_without_force(self) -> None:
        existing = {"oie": {"class_id": "keep"}}
        new_meta, action = apply_oie_fill_if_missing(
            existing, {"class_id": "new"}, force=False
        )
        self.assertIsNone(new_meta)
        self.assertEqual(action, "skipped_existing")

    def test_force_overwrites(self) -> None:
        existing = {"oie": {"class_id": "old"}, "other": 1}
        new_meta, action = apply_oie_fill_if_missing(
            existing, {"class_id": "new"}, force=True
        )
        self.assertEqual(action, "updated")
        assert new_meta is not None
        self.assertEqual(new_meta["oie"]["class_id"], "new")
        self.assertEqual(new_meta["other"], 1)

    def test_unchanged_seed_counts_as_unchanged(self) -> None:
        oie = {"class_id": "same"}
        new_meta, action = apply_oie_fill_if_missing({"oie": oie}, oie, force=True)
        self.assertIsNone(new_meta)
        self.assertEqual(action, "unchanged")


class CreOiePopulatedTest(unittest.TestCase):
    def test_oie_block(self) -> None:
        self.assertTrue(cre_oie_populated({"oie": {"families": ["ai"]}}))
        self.assertFalse(cre_oie_populated({}))
        self.assertFalse(cre_oie_populated(None))

    def test_legacy_mirrors(self) -> None:
        self.assertTrue(cre_oie_populated({"oie_families": ["cloud"]}))
        self.assertTrue(cre_oie_populated({"oie_classes": ["auth"]}))


class RequireOieBaseMetadataTest(unittest.TestCase):
    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_raises_when_taxonomy_and_cre_oie_empty(self) -> None:
        session = mock.Mock()
        # load_taxonomy_index_from_session queries Nodes; require also queries CRE.
        cre_q = mock.Mock()
        cre_q.all.return_value = [
            SimpleNamespace(metadata_json={}),
            SimpleNamespace(metadata_json=None),
        ]

        def query(model: Any) -> Any:
            name = getattr(model, "__name__", str(model))
            if name == "CRE" or "CRE" in str(model):
                return cre_q
            # Node queries inside load_taxonomy_index_from_session
            nq = mock.Mock()
            nq.filter.return_value = nq
            nq.all.return_value = [SimpleNamespace(metadata_json={})]
            return nq

        session.query.side_effect = query

        with self.assertRaises(OieMetadataNotPopulatedError) as ctx:
            require_oie_base_metadata(session)
        self.assertIn("oie-tag-base", str(ctx.exception))
        self.assertIn("Populate", str(ctx.exception))

    def test_passes_when_taxonomy_and_cre_oie_present(self) -> None:
        nodes = [
            SimpleNamespace(
                metadata_json={
                    "oie": {
                        "section_id": "API5",
                        "class_id": "function_authz",
                        "family": "access",
                    }
                }
            )
        ]
        cres = [
            SimpleNamespace(
                metadata_json={
                    "oie": {"families": ["access"], "classes": ["function_authz"]}
                }
            )
        ]

        def query(model: Any) -> Any:
            name = getattr(model, "__name__", "")
            if name == "CRE":
                cq = mock.Mock()
                cq.all.return_value = cres
                return cq
            nq = mock.Mock()
            nq.filter.return_value = nq
            nq.all.return_value = nodes
            return nq

        session = mock.Mock()
        session.query.side_effect = query
        tax = require_oie_base_metadata(session)
        self.assertIn("API5", tax.section_id_to_class)


class FactoryOieGateTest(unittest.TestCase):
    _BASELINE_ENV = {
        "CRE_LIBRARIAN_TEMPERATURE": "1.2",
        "CRE_LIBRARIAN_CRE_SUMMARY": "0",
        "CRE_LIBRARIAN_DUAL_INDEX": "0",
        "CRE_LIBRARIAN_PRIOR_CAGE": "0",
    }

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_build_components_raises_when_session_oie_empty(self) -> None:
        from application.utils.librarian.config_loader import load_config
        from application.utils.librarian.factory import build_components
        from application.utils.librarian.oie_taxonomy import POPULATE_INSTRUCTION

        class _Db:
            session = mock.Mock()
            embeddings: Dict[str, list[float]] = {"616-305": [0.1, 0.2, 0.3]}
            texts: Dict[str, str] = {"616-305": "password storage"}

            def get_embeddings_by_doc_type(self, doc_type: Any) -> Mapping[str, Any]:
                return self.embeddings if str(doc_type) == "CRE" else {}

            def get_embedding_contents_by_doc_type(
                self, doc_type: Any
            ) -> Mapping[str, str]:
                return self.texts if str(doc_type) == "CRE" else {}

            def can_use_pgvector_similarity(self) -> bool:
                return False

        # Session queries before the gate are best-effort; the gate itself raises.
        empty_q = mock.Mock()
        empty_q.filter.return_value = empty_q
        empty_q.join.return_value = empty_q
        empty_q.all.return_value = []
        _Db.session.query.return_value = empty_q

        with mock.patch(
            "application.utils.librarian.cross_encoder.build_cross_encoder_score_fn",
            return_value=lambda pairs: [0.0 for _ in pairs],
        ):
            with mock.patch(
                "application.utils.librarian.oie_taxonomy.require_oie_base_metadata",
                side_effect=OieMetadataNotPopulatedError(POPULATE_INSTRUCTION),
            ):
                with mock.patch.dict(os.environ, self._BASELINE_ENV, clear=True):
                    with self.assertRaises(OieMetadataNotPopulatedError) as ctx:
                        build_components(
                            _Db(),
                            config=load_config(),
                            embed_fn=lambda text: [0.1, 0.2, 0.3],
                        )
        self.assertIn("oie-tag-base", str(ctx.exception))


class TagScriptHelpersImportTest(unittest.TestCase):
    """Scripts stay importable for unit tests without a live DB."""

    def test_node_build_oie_for_catalog_section(self) -> None:
        scripts = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
        scripts = os.path.abspath(scripts)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import oie_tag_standard_sections as tag_nodes  # type: ignore[import-not-found]

        node = SimpleNamespace(
            section_id="API5",
            section="Broken Function Level Authorization",
            name="OWASP API Top 10",
        )
        oie = tag_nodes.build_node_oie(node)
        assert oie is not None
        self.assertEqual(oie["section_id"], "API5")
        self.assertEqual(oie["class_id"], "function_authz")


if __name__ == "__main__":
    unittest.main()
