import json
import unittest
from unittest.mock import Mock, patch

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs as defs
from application.utils.gap_analysis import (
    OPENCRE_STANDARD_NAME,
    backfill_opencre_direct_pairs,
    make_resources_key,
)


class TestOpencreGapAnalysis(unittest.TestCase):
    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def test_backfill_populates_secure_headers_pair_from_auto_linked_nodes(
        self,
    ) -> None:
        cre = self.collection.add_cre(
            defs.CRE(
                id="636-347",
                name="HTTP security headers",
                description="",
            )
        )
        header_node = self.collection.add_node(
            defs.Standard(
                name="Secure Headers",
                section="Prevent information disclosure via HTTP headers",
                hyperlink="https://owasp.org/example",
            )
        )
        self.collection.add_link(
            cre=cre,
            node=header_node,
            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
        )

        written = backfill_opencre_direct_pairs(self.collection, refresh=True)
        cache_key = make_resources_key([OPENCRE_STANDARD_NAME, "Secure Headers"])

        self.assertGreaterEqual(written, 1)
        self.assertTrue(self.collection.gap_analysis_exists(cache_key))
        payload = json.loads(self.collection.get_gap_analysis_result(cache_key))
        self.assertIn("636-347", payload["result"])
        path = next(iter(payload["result"]["636-347"]["paths"].values()))
        self.assertEqual("AUTOMATICALLY_LINKED_TO", path["path"][0]["relationship"])

    @patch(
        "application.utils.gap_analysis.build_direct_cre_overlap_map_analysis",
        return_value={"result": {"x": {}}},
    )
    def test_backfill_refresh_recomputes_cached_pairs(self, build_mock: Mock) -> None:
        collection = Mock()
        collection.standards.return_value = ["ASVS"]

        backfill_opencre_direct_pairs(collection, refresh=False)
        build_mock.assert_not_called()

        backfill_opencre_direct_pairs(collection, refresh=True)
        self.assertEqual(2, build_mock.call_count)

    @patch(
        "application.utils.gap_analysis.build_direct_cre_overlap_map_analysis",
        return_value={"result": {"x": {}}},
    )
    def test_backfill_missing_only_skips_when_cache_exists(
        self, build_mock: Mock
    ) -> None:
        collection = Mock()
        collection.standards.return_value = ["ASVS"]
        collection.gap_analysis_exists.return_value = True

        written = backfill_opencre_direct_pairs(collection, refresh=False)

        self.assertEqual(0, written)
        build_mock.assert_not_called()
